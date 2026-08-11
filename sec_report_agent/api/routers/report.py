"""报告 API — 任务列表 / 生成 / 详情 / 统计"""

import asyncio
from io import BytesIO

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from api.response import ok, fail, ApiCode
from api.auth_deps import require_login, require_analyst
from common.exception.exception import NotFoundError
from common.validator.validator import validate_enum
from infra.db.session import get_db
from infra.db.repositories import ReportTaskRepo
from model.enum.enums import ReportCycle, TaskStatus

router = APIRouter()


@router.get("/list")
def list_tasks(cycle: str | None = None, status: str | None = None,
               page: int = Query(1, ge=1), limit: int = Query(15, ge=1, le=100),
               _=Depends(require_login), db: Session = Depends(get_db)):
    """任务列表（分页）"""
    rows, total = ReportTaskRepo.list_all(db, cycle=cycle, status=status,
                                          offset=(page - 1) * limit, limit=limit)
    items = []
    for t in rows:
        try:
            cycle_label = ReportCycle(t.cycle).label
        except ValueError:
            cycle_label = t.cycle
        try:
            status_label = TaskStatus(t.status).label
        except ValueError:
            status_label = t.status
        items.append({
            "id": t.id, "cycle": t.cycle, "cycleLabel": cycle_label,
            "windowStart": t.window_start, "windowEnd": t.window_end,
            "status": t.status, "statusLabel": status_label,
            "triggerType": t.trigger_type, "errorMsg": t.error_msg,
            "durationMs": t.duration_ms, "dataSourceStats": t.data_source_stats,
            "startedAt": t.started_at, "finishedAt": t.finished_at,
            "createdAt": t.created_at,
        })
    return ok({"items": items, "total": total, "page": page, "limit": limit})


@router.post("/generate")
async def generate(body: dict, request: Request, _=Depends(require_analyst), db: Session = Depends(get_db)):
    """异步提交报告生成（V2.0 R：创建 PENDING 任务立即返回，后台执行）"""
    from app.services.report_service import ReportService
    from app.tasks.report_task import calc_window

    cycle = (body.get("cycle") or "").upper()
    validate_enum(cycle, [c.value for c in ReportCycle], "cycle")

    # B3 并发生成上限（V2.2）：RUNNING 任务达上限拒绝新提交，防打爆 LLM/DB
    from model.entity.entities import ReportTask
    from config.settings import settings as _settings
    running_count = db.query(ReportTask).filter(ReportTask.status == "RUNNING").count()
    if running_count >= _settings.max_concurrent_generation:
        return fail(
            f"并发生成任务已达上限（{_settings.max_concurrent_generation}），请稍后重试",
            ApiCode.BUSINESS_ERROR,
        )

    ws = body.get("windowStart") or None
    we = body.get("windowEnd") or None
    if not ws or not we:
        ws, we = calc_window(cycle)
    rerun = bool(body.get("rerun", False))

    result = await ReportService.submit(cycle, ws, we, trigger_type="MANUAL", rerun=rerun)
    if not result.get("reused"):
        # 后台执行（保留引用防 GC）
        task = asyncio.create_task(
            ReportService.run_background(result["task_id"], cycle, ws, we)
        )
        bg = getattr(request.app.state, "_bg_tasks", None)
        if bg is None:
            bg = set()
            request.app.state._bg_tasks = bg
        bg.add(task)
        task.add_done_callback(bg.discard)
    return ok(result, message="任务已创建，后台执行中")


@router.post("/qa")
async def report_qa(body: dict, _=Depends(require_login), db: Session = Depends(get_db)):
    """报告智能问答（V2.1）：基于报告正文 + 知识库参考回答分析师问题"""
    from app.services.report_qa_service import ReportQAService

    version_id = int(body.get("versionId") or body.get("version_id") or 0)
    question = str(body.get("question") or "").strip()
    if version_id <= 0:
        return fail("versionId 必填", ApiCode.PARAM_ERROR)
    if not question:
        return fail("question 必填", ApiCode.PARAM_ERROR)
    result = await ReportQAService.ask(db, version_id, question)
    return ok(result)


@router.get("/export/{version_id}")
def report_export(version_id: int, format: str = Query("md", pattern="^(md|docx)$"),
                  user=Depends(require_login), db: Session = Depends(get_db)):
    """报告导出（V2.1）：md / docx 文件下载；V2.3 导出审计留痕"""
    from fastapi.responses import StreamingResponse
    from app.services.report_export_service import ReportExportService
    from model.entity.entities import ReportVersion
    from infra.db.repositories import AuditLogRepo

    version = db.query(ReportVersion).filter(ReportVersion.id == version_id).first()
    if not version:
        return fail(f"报告版本不存在: {version_id}", ApiCode.NOT_FOUND)
    content_md = version.content_md or ""
    if format == "docx":
        payload = ReportExportService.build_docx(content_md)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"{version.title or 'report'}-v{version.version_no}.docx"
    else:
        payload = ReportExportService.build_markdown(content_md)
        media = "text/markdown; charset=utf-8"
        filename = f"{version.title or 'report'}-v{version.version_no}.md"
    filename = filename.replace("（", "(").replace("）", ")").replace(" ", "_")
    from urllib.parse import quote
    safe_name = quote(filename)  # 中文文件名需 URL 编码（headers 必须 latin-1 可编码）
    # V2.3 导出审计：留痕操作者/版本/格式（导出失败不阻断下载）
    try:
        AuditLogRepo.add(
            db, getattr(user, "username", "?"), "EXPORT_REPORT",
            target_type="ReportVersion", target_id=version_id,
            detail=f"导出报告 {format.upper()}，标题={version.title or ''}",
        )
        db.commit()
    except Exception:
        pass
    return StreamingResponse(
        BytesIO(payload),
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


@router.get("/status/{task_id}")
def task_status(task_id: int, _=Depends(require_login), db: Session = Depends(get_db)):
    """异步任务状态轮询（V2.0 R）"""
    from infra.db.repositories import ReportVersionRepo
    task = ReportTaskRepo.get(db, task_id)
    if not task:
        raise NotFoundError(f"任务不存在: {task_id}")
    version = ReportVersionRepo.get_latest_by_task(db, task_id)
    return ok({
        "id": task.id, "status": task.status, "cycle": task.cycle,
        "errorMsg": task.error_msg, "versionId": version.id if version else 0,
        "durationMs": task.duration_ms, "finishedAt": task.finished_at,
    })


@router.get("/detail/{task_id}")
def task_detail(task_id: int, _=Depends(require_login), db: Session = Depends(get_db)):
    """任务详情（含数据源统计 + 版本关联）"""
    from infra.db.repositories import ReportVersionRepo
    task = ReportTaskRepo.get(db, task_id)
    if not task:
        raise NotFoundError(f"任务不存在: {task_id}")
    version = ReportVersionRepo.get_latest_by_task(db, task_id)
    return ok({
        "id": task.id, "cycle": task.cycle, "windowStart": task.window_start,
        "windowEnd": task.window_end, "status": task.status,
        "triggerType": task.trigger_type, "errorMsg": task.error_msg,
        "dataSourceStats": task.data_source_stats,
        "startedAt": task.started_at, "finishedAt": task.finished_at,
        "durationMs": task.duration_ms, "traceId": task.trace_id,
        "versionId": version.id if version else 0,
        "createdAt": task.created_at,
    })


@router.get("/stats")
def task_stats(_=Depends(require_login), db: Session = Depends(get_db)):
    """五周期任务统计（供看板）"""
    rows, _ = ReportTaskRepo.list_all(db, limit=500)
    stats = {}
    for cycle in ReportCycle:
        cyc_rows = [r for r in rows if r.cycle == cycle.value]
        success = sum(1 for r in cyc_rows if r.status == TaskStatus.SUCCESS.value)
        failed = sum(1 for r in cyc_rows if r.status == TaskStatus.FAILED.value)
        stats[cycle.value] = {
            "label": cycle.label, "total": len(cyc_rows),
            "success": success, "failed": failed,
            "last": cyc_rows[0].finished_at if cyc_rows else None,
        }
    return ok(stats)


@router.post("/export-batch")
def report_export_batch(body: dict, user=Depends(require_analyst),
                        db: Session = Depends(get_db)):
    """批量导出/周期归档（V2.8）：按周期 + 窗口范围打包 ZIP（标准库 zipfile）"""
    import zipfile
    from fastapi.responses import StreamingResponse
    from model.entity.entities import ReportVersion
    from infra.db.repositories import AuditLogRepo

    cycle = (body.get("cycle") or "").upper()
    if cycle not in [c.value for c in ReportCycle]:
        return fail(f"cycle 非法: {cycle}", ApiCode.PARAM_ERROR)
    from_ = (body.get("from") or "").strip()
    to_ = (body.get("to") or "").strip()

    q = db.query(ReportVersion).filter(ReportVersion.cycle == cycle)
    # 窗口范围过滤（ISO 字符串字典序即时间序；注意日期与时间拼接的字典序坑）
    from datetime import datetime as _dt
    if from_:
        from_start = from_ if len(from_) >= 19 else f"{from_} 00:00:00"
        q = q.filter(ReportVersion.window_start >= from_start)
    if to_:
        if len(to_) >= 19:
            to_end = to_
        elif len(to_) == 7:  # YYYY-MM → 下月首日（开区间，避免 '-' < ' ' 字典序坑）
            y, m = int(to_[:4]), int(to_[5:7])
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            to_end = f"{ny:04d}-{nm:02d}-01 00:00:00"
        else:  # YYYY-MM-DD → 当日 23:59:59
            to_end = f"{to_} 23:59:59"
        q = q.filter(ReportVersion.window_start < to_end)
    versions = q.order_by(ReportVersion.window_start.desc()).limit(200).all()
    if not versions:
        return fail(f"{cycle} 周期 {from_ or '全部'}~{to_ or '全部'} 无报告版本",
                    ApiCode.NOT_FOUND)

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for v in versions:
            title = (v.title or f"report-{v.window_start[:10]}").replace("/", "-")
            fname = f"{cycle}_{v.window_start[:10]}_{title}.md"
            zf.writestr(fname, v.content_md or f"# {title}\n\n（无内容）")
    buf.seek(0)

    # 导出审计（V2.3 惯例）
    try:
        AuditLogRepo.add(
            db, getattr(user, "username", "?"), "EXPORT_REPORT_BATCH",
            target_type="ReportVersion", target_id=0,
            detail=f"批量导出 {cycle} {from_ or '全部'}~{to_ or '全部'}，共 {len(versions)} 份",
        )
        db.commit()
    except Exception:
        pass

    from urllib.parse import quote
    safe_name = quote(f"{cycle}_批量归档_{len(versions)}份.zip")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )
