"""站内通知 API（V2.8）— 列表 / 未读数 / 标记已读 / 全部已读"""

from fastapi import APIRouter, Depends, Query

from api.response import ok, fail, ApiCode
from api.auth_deps import require_login
from infra.db.session import get_db
from infra.db.repositories import NotificationRepo

router = APIRouter()


@router.get("/list")
def notification_list(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                      readFlag: str | None = None,
                      user=Depends(require_login), db=Depends(get_db)):
    """通知列表（当前用户：全体通知 + 本人定向通知）"""
    read_filter = None
    if readFlag in ("yes", "no"):
        read_filter = readFlag
    rows, total = NotificationRepo.list_all(
        db, target_user=getattr(user, "username", ""),
        read_flag=read_filter, page=page, limit=limit,
    )
    items = [{
        "id": n.id, "type": n.type, "title": n.title, "content": n.content,
        "level": n.level, "readFlag": n.read_flag,
        "taskId": n.task_id, "versionId": n.version_id, "createdAt": n.created_at,
    } for n in rows]
    return ok({"items": items, "total": total, "page": page, "limit": limit})


@router.get("/unread-count")
def notification_unread(user=Depends(require_login), db=Depends(get_db)):
    """未读通知数（顶栏红点）"""
    count = NotificationRepo.unread_count(db, getattr(user, "username", ""))
    return ok({"count": count})


@router.post("/read/{nid}")
def notification_read(nid: int, user=Depends(require_login), db=Depends(get_db)):
    """标记单条已读"""
    ok_flag = NotificationRepo.mark_read(db, nid, getattr(user, "username", ""))
    if not ok_flag:
        return fail(f"通知不存在或无权限: {nid}", ApiCode.NOT_FOUND)
    return ok({"id": nid, "readFlag": "yes"})


@router.post("/read-all")
def notification_read_all(user=Depends(require_login), db=Depends(get_db)):
    """全部标记已读"""
    count = NotificationRepo.mark_all_read(db, getattr(user, "username", ""))
    return ok({"marked": count})
