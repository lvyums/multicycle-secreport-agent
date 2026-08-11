"""V2.8 #6 站内通知中心 — repo 四方法 + 三类埋点（REPORT_READY/PUSH_FAIL/ALERT/REVIEW_RESULT）

通知表 sys_notification 是共享表，用例用 task_id/version_id 2099 段隔离 + teardown 清理。
"""

import pytest


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from infra.db.session import SessionLocal
    from model.entity.entities import Notification
    db = SessionLocal()
    try:
        db.query(Notification).delete()  # 测试库专用：清空通知表防残留
        db.commit()
    finally:
        db.close()


def test_add_and_unread_count():
    from infra.db.session import SessionLocal
    from infra.db.repositories import NotificationRepo
    db = SessionLocal()
    try:
        NotificationRepo.add(db, "ALERT", "测试告警", "内容", task_id=990100)
        assert NotificationRepo.unread_count(db, target_user="") == 1
        assert NotificationRepo.unread_count(db, target_user="ut-admin") == 1  # 全体可见
        assert NotificationRepo.unread_count(db, target_user="ut-analyst") == 1
    finally:
        db.close()


def test_target_user_scope():
    """定向通知只对目标用户可见"""
    from infra.db.session import SessionLocal
    from infra.db.repositories import NotificationRepo
    db = SessionLocal()
    try:
        NotificationRepo.add(db, "REVIEW_RESULT", "审核", "定向", target_user="ut-analyst",
                             task_id=990101)
        assert NotificationRepo.unread_count(db, target_user="ut-analyst") == 1
        assert NotificationRepo.unread_count(db, target_user="ut-admin") == 0
    finally:
        db.close()


def test_mark_read_and_all():
    from infra.db.session import SessionLocal
    from infra.db.repositories import NotificationRepo
    db = SessionLocal()
    try:
        n1 = NotificationRepo.add(db, "ALERT", "告警A", "", task_id=990102)
        n2 = NotificationRepo.add(db, "ALERT", "告警B", "", task_id=990102)
        assert NotificationRepo.mark_read(db, n1.id) is True
        assert NotificationRepo.unread_count(db, target_user="") == 1
        assert NotificationRepo.mark_all_read(db, target_user="") == 1
        assert NotificationRepo.unread_count(db, target_user="") == 0
    finally:
        db.close()


def test_report_ready_embed():
    """REPORT_READY 埋点：生成完成 → admin 可见通知"""
    from app.services.notification_service import NotificationService
    from infra.db.session import SessionLocal
    from infra.db.repositories import NotificationRepo
    NotificationService.report_ready("MONTHLY", "2099-01-01 00:00:00", "2099-02-01 00:00:00",
                                     990100, 990100)
    db = SessionLocal()
    try:
        assert NotificationRepo.unread_count(db, target_user="admin") >= 1
        rows, _ = NotificationRepo.list_all(db, target_user="admin", limit=10)
        assert any(n.type == "REPORT_READY" for n in rows)
    finally:
        db.close()


def test_push_fail_embed():
    from app.services.notification_service import NotificationService
    from infra.db.session import SessionLocal
    from infra.db.repositories import NotificationRepo
    NotificationService.push_fail("MONTHLY", "email", 990100, "SMTP 超时")
    db = SessionLocal()
    try:
        rows, _ = NotificationRepo.list_all(db, target_user="admin", limit=10)
        assert any(n.type == "PUSH_FAIL" and "email" in n.title for n in rows)
    finally:
        db.close()


def test_alert_fired_embed():
    """告警器 _fire 埋点 → ALERT 通知"""
    from infra.db.session import SessionLocal
    from infra.db.repositories import NotificationRepo
    from infra.alert.alerter import Alerter
    db = SessionLocal()
    try:
        Alerter()._fire(db, "ut_rule", "UT 规则", 5.0, "测试触发 5.0")
        rows, _ = NotificationRepo.list_all(db, target_user="admin", limit=10)
        assert any(n.type == "ALERT" and "UT 规则" in n.title for n in rows)
    finally:
        db.close()


def test_review_result_embed():
    """审核动作 → REVIEW_RESULT 通知创建人（version.operator）"""
    from fastapi.testclient import TestClient
    from main import app
    from infra.db.session import SessionLocal
    from infra.db.repositories import NotificationRepo
    from model.entity.entities import ReportVersion
    from api.auth_deps import get_current_user
    from model.entity.entities import User

    db = SessionLocal()
    try:
        ver = ReportVersion(
            task_id=990101, cycle="WEEKLY",
            window_start="2099-01-01 00:00:00", window_end="2099-01-08 00:00:00",
            version_no=1, version_type="AI_DRAFT", status="DRAFT",
            title="UT-REVIEW", content_md="# 审核测试", file_path="",
            operator="ut-analyst",
        )
        db.add(ver)
        db.commit()
        db.refresh(ver)
        vid = ver.id
    finally:
        db.close()

    client = TestClient(app)
    old = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: User(
        id=2, username="ut-admin", role="admin", enabled="enabled")
    try:
        r = client.post(f"/api/version/audit/submit/{vid}", json={"operator": "ut-analyst"})
        assert r.status_code == 200, r.text
        r = client.post(f"/api/version/audit/approve/{vid}", json={"operator": "ut-admin"})
        assert r.status_code == 200, r.text
    finally:
        if old is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = old

    db = SessionLocal()
    try:
        rows, _ = NotificationRepo.list_all(db, target_user="ut-analyst", limit=20)
        assert any(n.type == "REVIEW_RESULT" and n.version_id == vid for n in rows), rows
    finally:
        db.close()
