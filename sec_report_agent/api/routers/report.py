"""报告 API — 任务列表 / 生成 / 详情 / 统计"""

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.response import ok, fail, ApiCode
from common.exception.exception import NotFoundError
from common.validator.validator import validate_enum
from infra.db.session import get_db
from infra.db.repositories import ReportTaskRepo
from model.enum.enums import ReportCycle, TaskStatus

router = APIRouter()


@router.get("/list")
def list_tasks(cycle: str | None = None, status: str | None = None,
               page: int = Query(1, ge=1), limit: int = Query(15, ge=1, le=100),
               db: Session = Depends(get_db)):
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
async def generate(body: dict, db: Session = Depends(get_db)):
    """手动生成报告（cycle 必填；窗口缺省按周期计算）"""
    from app.services.report_service import ReportService
    from app.tasks.report_task import calc_window

    cycle = (body.get("cycle") or "").upper()
    validate_enum(cycle, [c.value for c in ReportCycle], "cycle")

    ws = body.get("windowStart") or None
    we = body.get("windowEnd") or None
    if not ws or not we:
        ws, we = calc_window(cycle)
    rerun = bool(body.get("rerun", False))

    result = await ReportService.generate(cycle, ws, we, trigger_type="MANUAL", rerun=rerun)
    return ok(result, message="任务已创建/复用")


@router.get("/detail/{task_id}")
def task_detail(task_id: int, db: Session = Depends(get_db)):
    """任务详情（含数据源统计）"""
    task = ReportTaskRepo.get(db, task_id)
    if not task:
        raise NotFoundError(f"任务不存在: {task_id}")
    return ok({
        "id": task.id, "cycle": task.cycle, "windowStart": task.window_start,
        "windowEnd": task.window_end, "status": task.status,
        "triggerType": task.trigger_type, "errorMsg": task.error_msg,
        "dataSourceStats": task.data_source_stats,
        "startedAt": task.started_at, "finishedAt": task.finished_at,
        "durationMs": task.duration_ms, "traceId": task.trace_id,
        "createdAt": task.created_at,
    })


@router.get("/stats")
def task_stats(db: Session = Depends(get_db)):
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
