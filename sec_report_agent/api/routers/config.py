"""报告选配 API — 章节开关 / 周期 / 推送渠道 / 自动生成（V1.3，单例配置）"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.response import ok
from api.auth_deps import require_login, require_admin, require_analyst
from infra.db.session import get_db
from infra.db.repositories import ReportConfigRepo
from common.exception.exception import BusinessError

router = APIRouter()

VALID_SECTIONS = {"overview", "alert", "vuln", "attack", "trend", "suggestion"}
VALID_CYCLES = {"DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"}


@router.get("/get")
def config_get(_=Depends(require_login), db: Session = Depends(get_db)):
    """获取报告选配（不存在则建默认）"""
    cfg = ReportConfigRepo.get_or_create(db)
    return ok({
        "id": cfg.id,
        "enabledCycles": cfg.enabled_cycles,
        "sections": cfg.sections,
        "pushChannels": cfg.push_channels,
        "autoGenerate": cfg.auto_generate,
        "updatedAt": cfg.updated_at,
    })


@router.post("/save")
def config_save(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    """保存报告选配"""
    cfg = ReportConfigRepo.get_or_create(db)
    sections = body.get("sections")
    if sections is not None:
        if not isinstance(sections, dict) or not set(sections) <= VALID_SECTIONS:
            raise BusinessError(f"章节配置非法: {sections}")
        for k in VALID_SECTIONS:
            sections.setdefault(k, True)
    cycles = body.get("enabledCycles")
    if cycles is not None:
        if not isinstance(cycles, list) or not set(cycles) <= VALID_CYCLES:
            raise BusinessError(f"周期配置非法: {cycles}")
    channels = body.get("pushChannels")
    if channels is not None and not isinstance(channels, list):
        raise BusinessError("推送渠道必须是列表")
    auto = body.get("autoGenerate")
    if auto is not None and auto not in ("enabled", "disabled"):
        raise BusinessError("autoGenerate 只能是 enabled/disabled")

    ReportConfigRepo.save(
        db, cfg,
        sections=sections if sections is not None else cfg.sections,
        enabled_cycles=cycles if cycles is not None else cfg.enabled_cycles,
        push_channels=channels if channels is not None else cfg.push_channels,
        auto_generate=auto if auto is not None else cfg.auto_generate,
    )
    return ok({"id": cfg.id, "updatedAt": cfg.updated_at})
