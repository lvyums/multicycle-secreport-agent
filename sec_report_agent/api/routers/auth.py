"""认证 API — 登录 / 当前用户 / 改密 / 用户管理（V2.0 RBAC + V2.2 安全加固）"""

import re
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.response import ok, fail, ApiCode
from api.auth_deps import get_current_user, require_admin
from config.settings import settings
from infra.db.session import get_db
from infra.db.repositories import UserRepo, AuditLogRepo
from app.services import auth_service

router = APIRouter()


def _user_vo(user) -> dict:
    return {
        "id": user.id, "username": user.username,
        "role": user.role, "displayName": user.display_name,
        "mustChangePwd": getattr(user, "must_change_pwd", "no") == "yes",
    }


@router.post("/login")
def login(body: dict, db: Session = Depends(get_db)):
    """用户名密码登录 → token（V2.2：失败锁定 + 强制改密标记）"""
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名与密码必填")
    user = UserRepo.get_by_username(db, username)
    if not user or user.enabled != "enabled":
        # 用户不存在/禁用也计入失败锁定（防枚举），但直接返回通用错误
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    # 锁定检查
    locked_until = getattr(user, "locked_until", "") or ""
    if locked_until:
        try:
            locked_ts = time.mktime(time.strptime(locked_until, "%Y-%m-%d %H:%M:%S"))
            if locked_ts > time.time():
                remain_min = int((locked_ts - time.time()) / 60) + 1
                raise HTTPException(status_code=423, detail=f"账号已锁定，请 {remain_min} 分钟后重试")
        except ValueError:
            pass  # 时间格式异常视为未锁定
    if not auth_service.verify_password(password, user.password_hash):
        # 失败计数 + 审计
        user.login_fail_count = int(getattr(user, "login_fail_count", 0) or 0) + 1
        if user.login_fail_count >= settings.login_fail_limit:
            user.locked_until = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(time.time() + settings.login_lock_minutes * 60),
            )
            user.login_fail_count = 0
            AuditLogRepo.add(db, operator=username, action="LOGIN_FAIL",
                             target_type="User", target_id=user.id,
                             detail=f"连续失败达 {settings.login_fail_limit} 次，锁定 {settings.login_lock_minutes} 分钟")
        else:
            AuditLogRepo.add(db, operator=username, action="LOGIN_FAIL",
                             target_type="User", target_id=user.id,
                             detail=f"密码错误（第 {user.login_fail_count} 次）")
        db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    # 成功：清零计数与锁定
    if int(getattr(user, "login_fail_count", 0) or 0) != 0:
        user.login_fail_count = 0
    if getattr(user, "locked_until", "") or "":
        user.locked_until = ""
    db.commit()
    token = auth_service.create_token(user.id, user.username, user.role)
    return ok({
        "token": token,
        "user": _user_vo(user),
    })


@router.get("/me")
def me(user=Depends(get_current_user)):
    """当前登录用户信息（含强制改密标记）"""
    return ok(_user_vo(user))


@router.post("/change-pwd")
def change_pwd(body: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """修改自己的密码（V2.2：强度校验 + 清强制改密标记）"""
    from model.entity.entities import User as UserEntity
    # 用端点 db 重新加载（注入对象可能 detached，直接修改再 commit 会丢失）
    db_user = db.get(UserEntity, user.id)
    if db_user is None:
        return fail("用户不存在", ApiCode.NOT_FOUND)
    old_pwd = body.get("oldPwd") or ""
    new_pwd = body.get("newPwd") or ""
    if not old_pwd or not new_pwd:
        return fail("旧密码与新密码必填", ApiCode.PARAM_ERROR)
    if not auth_service.verify_password(old_pwd, db_user.password_hash):
        return fail("旧密码不正确", ApiCode.PARAM_ERROR)
    if len(new_pwd) < settings.pwd_min_length:
        return fail(f"新密码至少 {settings.pwd_min_length} 位", ApiCode.PARAM_ERROR)
    if not (re.search(r"[A-Za-z]", new_pwd) and re.search(r"\d", new_pwd)):
        return fail("新密码需同时包含字母与数字", ApiCode.PARAM_ERROR)
    if new_pwd == old_pwd:
        return fail("新密码不能与旧密码相同", ApiCode.PARAM_ERROR)
    db_user.password_hash = auth_service.hash_password(new_pwd)
    db_user.must_change_pwd = "no"
    db.commit()
    AuditLogRepo.add(db, operator=db_user.username, action="CHANGE_PWD",
                     target_type="User", target_id=db_user.id, detail="修改密码")
    return ok({"id": db_user.id}, message="密码修改成功，请重新登录")


@router.get("/users")
def list_users(_=Depends(require_admin), db: Session = Depends(get_db)):
    """用户列表（仅 admin）"""
    users = UserRepo.list_all(db)
    return ok({"items": [
        {"id": u.id, "username": u.username, "role": u.role,
         "displayName": u.display_name, "enabled": u.enabled,
         "mustChangePwd": getattr(u, "must_change_pwd", "no") == "yes"}
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
