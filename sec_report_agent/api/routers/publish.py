"""推送 API — 报告交付（V1.1 仅 local 本地归档）"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.response import ok
from infra.db.session import get_db
from infra.db.repositories import PushLogRepo, ReportVersionRepo
from common.exception.exception import NotFoundError

router = APIRouter()


@router.post("/push")
def push_report(body: dict, db: Session = Depends(get_db)):
    """推送报告版本到指定渠道（默认 local）"""
    from capability.push.push_strategy import PushStrategyFactory
    from capability.push.local_strategy import LocalPushStrategy
    from capability.push.webhook_strategies import DingTalkPushStrategy, WeComPushStrategy, EmailPushStrategy

    PushStrategyFactory.register(LocalPushStrategy)
    PushStrategyFactory.register(DingTalkPushStrategy)
    PushStrategyFactory.register(WeComPushStrategy)
    PushStrategyFactory.register(EmailPushStrategy)

    version_id = body.get("versionId")
    channel = body.get("channel") or "local"
    if not version_id:
        from common.exception.exception import BusinessError
        raise BusinessError("缺少 versionId", code=400)

    ver = ReportVersionRepo.get(db, version_id)
    if not ver:
        raise NotFoundError(f"版本不存在: {version_id}")

    strategy = PushStrategyFactory.get(channel)
    version_info = {
        "version_id": ver.id, "title": ver.title, "file_path": ver.file_path,
        "content_md": ver.content_md, "cycle": ver.cycle, "version_no": ver.version_no,
    }
    result = strategy.push(version_info)

    PushLogRepo.create(
        db, version_id=version_id, channel=channel,
        status="SUCCESS" if result.success else "FAILED",
        detail=result.detail[:400],
    )
    return ok(result.to_dict(), message="推送成功" if result.success else "推送失败")


@router.get("/records")
def push_records(versionId: int, db: Session = Depends(get_db)):
    """版本推送记录"""
    rows = PushLogRepo.list_by_version(db, versionId)
    return ok([{
        "id": r.id, "versionId": r.version_id, "channel": r.channel,
        "status": r.status, "detail": r.detail, "createdAt": r.created_at,
    } for r in rows])


@router.get("/channels")
def push_channels():
    """可用推送渠道"""
    from capability.push.push_strategy import PushStrategyFactory
    from capability.push.local_strategy import LocalPushStrategy
    from capability.push.webhook_strategies import DingTalkPushStrategy, WeComPushStrategy, EmailPushStrategy

    PushStrategyFactory.register(LocalPushStrategy)
    PushStrategyFactory.register(DingTalkPushStrategy)
    PushStrategyFactory.register(WeComPushStrategy)
    PushStrategyFactory.register(EmailPushStrategy)
    return ok({"channels": PushStrategyFactory.available_channels()})
