"""认证 API — 登录 / 当前用户 / 用户管理（V2.0 RBAC）"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.response import ok
from api.auth_deps import get_current_user, require_admin
from infra.db.session import get_db
from infra.db.repositories import UserRepo
from app.services import auth_service

router = APIRouter()


@router.post("/login")
def login(body: dict, db: Session = Depends(get_db)):
    """用户名密码登录 → token"""
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名与密码必填")
    user = UserRepo.get_by_username(db, username)
    if not user or user.enabled != "enabled":
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not auth_service.verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth_service.create_token(user.id, user.username, user.role)
    return ok({
        "token": token,
        "user": {
            "id": user.id, "username": user.username,
            "role": user.role, "displayName": user.display_name,
        },
    })


@router.get("/me")
def me(user=Depends(get_current_user)):
    """当前登录用户信息"""
    return ok({
        "id": user.id, "username": user.username,
        "role": user.role, "displayName": user.display_name,
    })


@router.get("/users")
def list_users(_=Depends(require_admin), db: Session = Depends(get_db)):
    """用户列表（仅 admin）"""
    users = UserRepo.list_all(db)
    return ok({"items": [
        {"id": u.id, "username": u.username, "role": u.role,
         "displayName": u.display_name, "enabled": u.enabled}
        for u in users
    ]})


@router.post("/users/create")
def create_user(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    """新建用户（仅 admin）"""
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role") or "viewer"
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名与密码必填")
    if role not in ("admin", "analyst", "viewer"):
        raise HTTPException(status_code=400, detail="非法角色")
    if UserRepo.get_by_username(db, username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = UserRepo.create(
        db, username, auth_service.hash_password(password),
        role, body.get("displayName") or username,
    )
    return ok({"id": user.id, "username": user.username, "role": user.role})


@router.post("/users/toggle")
def toggle_user(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    """启停用户（仅 admin）"""
    user = UserRepo.get(db, body.get("id") or 0)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.enabled = "disabled" if user.enabled == "enabled" else "enabled"
    db.commit()
    db.refresh(user)
    return ok({"id": user.id, "enabled": user.enabled})


@router.post("/users/reset-pwd")
def reset_pwd(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    """重置密码（仅 admin）"""
    user = UserRepo.get(db, body.get("id") or 0)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    pwd = body.get("password") or ""
    if len(pwd) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    user.password_hash = auth_service.hash_password(pwd)
    db.commit()
    return ok({"id": user.id})
