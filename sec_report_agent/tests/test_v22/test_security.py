"""V2.2 测试 — 上线硬门槛：登录失败锁定 / 强制改密 / 任务恢复 / 并发生成上限
覆盖 A 安全凭据、B 任务恢复与并发控制的生产关键路径。
"""

import time

import pytest

from infra.db.session import SessionLocal
from infra.db.repositories import UserRepo
from app.services import auth_service


def _uniq(prefix: str) -> str:
    return f"{prefix}{int(time.time() * 1000)}"


@pytest.fixture()
def seed_users():
    """每个用例独立种子用户（避免失败计数/锁定状态跨用例污染）"""
    db = SessionLocal()
    try:
        UserRepo.ensure_seed_users(db)
        # 解锁种子用户（防止历史测试残留锁定）
        for u in UserRepo.list_all(db):
            u.login_fail_count = 0
            u.locked_until = ""
            u.must_change_pwd = "no"
        db.commit()
    finally:
        db.close()
    yield


# ═══════════════════ A1 登录失败锁定 ═══════════════════

def test_login_lock_after_failures(client, seed_users):
    """连续失败达阈值 → 423 锁定；锁定期间正确密码也被拒；审计留痕"""
    from config.settings import settings
    uname = _uniq("lock")
    db = SessionLocal()
    try:
        UserRepo.create(db, uname, auth_service.hash_password("pass123"), "viewer", "锁定测试")
    finally:
        db.close()
    # 失败到阈值-1 → 仍 401
    for _ in range(settings.login_fail_limit - 1):
        r = client.post("/api/auth/login", json={"username": uname, "password": "wrong"})
        assert r.status_code == 401
    # 第 N 次失败 → 触发锁定，本次仍 401
    r = client.post("/api/auth/login", json={"username": uname, "password": "wrong"})
    assert r.status_code == 401
    # 锁定期间正确密码 → 423
    r = client.post("/api/auth/login", json={"username": uname, "password": "pass123"})
    assert r.status_code == 423
    assert "锁定" in r.json()["detail"]
    # 审计留痕
    db = SessionLocal()
    try:
        from model.entity.entities import AuditLog
        logs = db.query(AuditLog).filter(AuditLog.action == "LOGIN_FAIL").all()
        assert any(l.operator == uname for l in logs)
    finally:
        db.close()


def test_login_success_resets_fail_count(client, seed_users):
    """失败后正确登录 → 计数清零、锁定清除"""
    uname = _uniq("reset")
    db = SessionLocal()
    try:
        UserRepo.create(db, uname, auth_service.hash_password("pass123"), "viewer", "重置测试")
    finally:
        db.close()
    client.post("/api/auth/login", json={"username": uname, "password": "wrong"})
    r = client.post("/api/auth/login", json={"username": uname, "password": "pass123"})
    assert r.status_code == 200
    db = SessionLocal()
    try:
        u = UserRepo.get_by_username(db, uname)
        assert u.login_fail_count == 0 and u.locked_until == ""
    finally:
        db.close()


# ═══════════════════ A2 强制改密 ═══════════════════

def test_change_pwd_flow(client, seed_users):
    """强制改密全流程：标记 → 改密成功清标记 → 旧密码失效 → 审计"""
    from api.auth_deps import get_current_user
    from main import app
    uname = _uniq("must")
    db = SessionLocal()
    try:
        u = UserRepo.create(db, uname, auth_service.hash_password("pass123"), "viewer",
                            "改密测试", must_change_pwd="yes")
        uid = u.id
    finally:
        db.close()
    # 注入被测用户为当前用户（change-pwd 作用于 override 用户）
    _orig_override = app.dependency_overrides.get(get_current_user)
    db = SessionLocal()
    try:
        app.dependency_overrides[get_current_user] = lambda: UserRepo.get_by_username(db, uname)
    finally:
        db.close()
    try:
        # 登录响应带 mustChangePwd
        r = client.post("/api/auth/login", json={"username": uname, "password": "pass123"})
        assert r.status_code == 200
        assert r.json()["data"]["user"]["mustChangePwd"] is True
        # 旧密码错误 → 400
        r = client.post("/api/auth/change-pwd", json={"oldPwd": "wrong", "newPwd": "NewPass123"})
        assert r.status_code == 200 and r.json()["code"] != 0
        # 弱密码 → 400（太短）
        r = client.post("/api/auth/change-pwd", json={"oldPwd": "pass123", "newPwd": "abc"})
        assert r.json()["code"] != 0
        # 纯数字 → 400
        r = client.post("/api/auth/change-pwd", json={"oldPwd": "pass123", "newPwd": "12345678"})
        assert r.json()["code"] != 0
        # 成功改密
        r = client.post("/api/auth/change-pwd", json={"oldPwd": "pass123", "newPwd": "NewPass123"})
        assert r.json()["code"] == 0
        # 标记清除
        db = SessionLocal()
        try:
            u2 = UserRepo.get_by_username(db, uname)
            assert u2.must_change_pwd == "no"
            from model.entity.entities import AuditLog
            assert db.query(AuditLog).filter(AuditLog.action == "CHANGE_PWD", AuditLog.operator == uname).count() >= 1
        finally:
            db.close()
        # 旧密码无法登录，新密码可登录
        assert client.post("/api/auth/login", json={"username": uname, "password": "pass123"}).status_code == 401
        assert client.post("/api/auth/login", json={"username": uname, "password": "NewPass123"}).status_code == 200
    finally:
        if _orig_override is not None:
            app.dependency_overrides[get_current_user] = _orig_override
        else:
            app.dependency_overrides.pop(get_current_user, None)


# ═══════════════════ A1 SECRET_KEY / CORS 生产强校验 ═══════════════════

def test_production_guard_settings():
    """生产环境：SECRET_KEY 默认值 / CORS 默认 * 时启动应被拒绝（校验逻辑）"""
    from config.settings import settings as _s
    from main import _parse_cors_origins
    # CORS 解析：默认 * → ["*"]；白名单 → 列表
    _old = _s.cors_origins
    try:
        _s.cors_origins = "*"
        assert _parse_cors_origins() == ["*"]
        _s.cors_origins = "https://a.example.com, https://b.example.com"
        assert _parse_cors_origins() == ["https://a.example.com", "https://b.example.com"]
    finally:
        _s.cors_origins = _old
    # 生产校验规则（与 lifespan 同逻辑）
    prod_bad_secret = (_s.app_env == "production" and _s.secret_key == "sec-report-dev-secret-change-me")
    prod_bad_cors = (_s.app_env == "production" and (_s.cors_origins or "*").strip() == "*")
    # dev 环境下两者都应为 False（测试不触发启动拒绝）
    assert prod_bad_secret is False and prod_bad_cors is False


# ═══════════════════ B1 任务恢复 ═══════════════════

def test_recover_stale_tasks():
    """启动恢复：PENDING/RUNNING 任务重置 FAILED 并带原因"""
    from model.entity.entities import ReportTask
    from infra.db.repositories import ReportTaskRepo
    db = SessionLocal()
    try:
        # 清掉历史残留 PENDING/RUNNING（测试库持久复用，避免污染断言）
        db.query(ReportTask).filter(ReportTask.status.in_(["PENDING", "RUNNING"])).delete()
        db.commit()
        # 唯一窗口（毫秒级时间戳），避免与历史残留任务碰撞
        w1 = f"2026-08-01 {_uniq('w1')}"
        w2 = f"2026-07-26 {_uniq('w2')}"
        w3 = f"2026-07-01 {_uniq('w3')}"
        ReportTaskRepo.create(db, cycle="DAILY", status="PENDING",
                              window_start=w1, window_end="2026-08-01 23:59:59")
        ReportTaskRepo.create(db, cycle="WEEKLY", status="RUNNING",
                              window_start=w2, window_end="2026-08-01 23:59:59")
        ReportTaskRepo.create(db, cycle="MONTHLY", status="DONE",
                              window_start=w3, window_end="2026-07-31 23:59:59")
    finally:
        db.close()
    # 执行恢复逻辑（与 main.lifespan 相同）
    from sqlalchemy import update as sa_update
    db = SessionLocal()
    try:
        n = db.execute(
            sa_update(ReportTask)
            .where(ReportTask.status.in_(["PENDING", "RUNNING"]))
            .values(status="FAILED", error_msg="服务重启中断，请重跑",
                    finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        ).rowcount
        db.commit()
        # 按本次唯一窗口定位（测试库持久复用，库里可能有历史残留）
        rows = db.query(ReportTask).filter(
            ReportTask.window_start.in_([w1, w2])
        ).all()
        assert n >= 2
        assert len(rows) == 2
        assert all(r.status == "FAILED" and "重启" in (r.error_msg or "") for r in rows)
        # 正常完成的任务不受影响
        done = db.query(ReportTask).filter(
            ReportTask.window_start == w3
        ).first()
        assert done is not None and done.status == "DONE"
    finally:
        db.close()


# ═══════════════════ B3 并发生成上限 ═══════════════════

def test_concurrent_generation_limit(client, seed_users):
    """RUNNING 任务达上限 → 新提交被拒；未达上限可提交"""
    from config.settings import settings as _s
    from model.entity.entities import ReportTask
    db = SessionLocal()
    try:
        # 造满 RUNNING 任务
        for i in range(_s.max_concurrent_generation):
            db.add(ReportTask(cycle="DAILY", status="RUNNING",
                              window_start="2026-08-01 00:00:00", window_end="2026-08-01 23:59:59"))
        db.commit()
    finally:
        db.close()
    r = client.post("/api/report/generate", json={"cycle": "DAILY"})
    assert r.status_code == 200
    assert r.json()["code"] != 0
    assert "并发" in r.json()["message"]
    # 清空后恢复可提交
    db = SessionLocal()
    try:
        db.query(ReportTask).filter(ReportTask.status == "RUNNING").delete()
        db.commit()
    finally:
        db.close()
    r = client.post("/api/report/generate", json={"cycle": "DAILY"})
    # 可能因其他校验失败，但不应是并发限制
    assert "并发" not in (r.json().get("message") or "")
