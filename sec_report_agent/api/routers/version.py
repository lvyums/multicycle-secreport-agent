"""版本 API — 列表 / 详情 / 内容 / 下载 / 审核流转 / 版本对比"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from api.response import ok
from api.auth_deps import require_login, require_admin, require_analyst
from app.services.version_service import VersionService
from common.exception.exception import NotFoundError
from infra.db.session import get_db
from infra.db.repositories import ReportVersionRepo
from model.enum.enums import ReportCycle, ReportStatus

router = APIRouter()


@router.get("/list")
def version_list(cycle: str | None = None, page: int = Query(1, ge=1),
                 limit: int = Query(15, ge=1, le=100), keyword: str | None = None,
                 _=Depends(require_login)):
    """版本列表（分页，可按周期/关键词过滤）"""
    if cycle:
        cycle = cycle.upper()
        if cycle not in [c.value for c in ReportCycle]:
            return ok({"items": [], "total": 0, "page": page, "limit": limit})
    data = VersionService.list_all(cycle=cycle, page=page, limit=limit, keyword=keyword)
    for item in data["items"]:
        try:
            item["cycleLabel"] = ReportCycle(item["cycle"]).label
        except ValueError:
            item["cycleLabel"] = item["cycle"]
    return ok(data)


@router.get("/detail/{version_id}")
def version_detail(version_id: int, _=Depends(require_login)):
    """版本详情"""
    return ok(VersionService.get(version_id))


@router.get("/content/{version_id}")
def version_content(version_id: int, _=Depends(require_login)):
    """版本内容（Markdown 文本，供前端预览）"""
    return ok(VersionService.get_content(version_id))


@router.get("/download/{version_id}")
def version_download(version_id: int, _=Depends(require_login)):
    """下载报告文件（存在返回文件，否则实时落盘）"""
    info = VersionService.get_download(version_id)
    path = info["path"]
    if not path:
        raise NotFoundError(f"版本 {version_id} 无内容可下载")
    return FileResponse(
        path, filename=path.split("/")[-1],
        media_type="application/octet-stream",
    )


# ═══════════ 审核流转（V1.2） ═══════════

@router.post("/audit/{action}/{version_id}")
def version_audit(action: str, version_id: int, body: dict | None = None,
                  db=Depends(get_db), _=Depends(require_analyst)):
    """审核流转：submit(提交审核) / approve(通过) / reject(驳回) / archive(归档)"""
    from app.services.audit_service import AuditService

    body = body or {}
    operator = body.get("operator") or "system"
    remark = body.get("remark") or ""

    ver = ReportVersionRepo.get(db, version_id)
    if not ver:
        raise NotFoundError(f"版本不存在: {version_id}")

    new_status = AuditService.transition(ver, action, operator=operator, remark=remark)
    db.commit()
    AuditService.log_audit(db, version_id, action, operator,
                           detail=f"{action}: {ver.title} → {new_status}",
                           trace_id=body.get("traceId") or "")
    # V2.8 站内通知：审核结果通知报告创建人
    if action in ("approve", "reject", "archive"):
        try:
            from app.services.notification_service import NotificationService
            NotificationService.review_result(version_id, action, operator,
                                              ver.operator or "", remark=remark)
        except Exception:
            pass
    db.commit()
    return ok({"versionId": version_id, "status": new_status,
               "statusLabel": ReportStatus(new_status).label})


@router.get("/audit/history/{version_id}")
def version_audit_history(version_id: int, db=Depends(get_db), _=Depends(require_login)):
    """版本审核记录"""
    from infra.db.repositories import AuditLogRepo
    rows = AuditLogRepo.list_by_target(db, "ReportVersion", version_id)
    return ok([{
        "id": r.id, "action": r.action, "operator": r.operator,
        "detail": r.detail, "createdAt": r.created_at,
    } for r in rows])


# ═══════════ 版本对比（V1.2） ═══════════

@router.get("/compare")
def version_compare(baseId: int = Query(..., ge=1), targetId: int = Query(..., ge=1),
                    db=Depends(get_db), _=Depends(require_login)):
    """版本对比：指标 diff + 章节文本 diff"""
    from app.services.version_service import VersionCompareService
    return ok(VersionCompareService.compare(db, baseId, targetId))
