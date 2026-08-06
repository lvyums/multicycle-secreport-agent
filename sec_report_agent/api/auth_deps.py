"""认证/授权依赖（V2.0 RBAC）— get_current_user / require_role"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from infra.db.session import get_db
from infra.db.repositories import UserRepo
from app.services import auth_service

ROLE_ORDER = {"viewer": 1, "analyst": 2, "admin": 3}


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """解析 Bearer token → User；无效则 401"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或凭证缺失")
    payload = auth_service.parse_token(authorization[7:].strip())
    if not payload:
        raise HTTPException(status_code=401, detail="凭证无效或已过期")
    user = UserRepo.get_by_username(db, payload.get("user", ""))
    if not user or user.enabled != "enabled":
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


def require_role(min_role: str):
    """角色门槛：viewer < analyst < admin"""
    def _dep(user=Depends(get_current_user)):
        if ROLE_ORDER.get(user.role, 0) < ROLE_ORDER.get(min_role, 0):
            raise HTTPException(status_code=403, detail=f"需要 {min_role} 及以上权限")
        return user
    return _dep


require_login = require_role("viewer")
require_analyst = require_role("analyst")
require_admin = require_role("admin")
