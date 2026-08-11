"""V2.8 #5 EMPTY 推送策略 — skip / alert_only / push 三态

测试库持久 SQLite（test_sec_report.db），数据 2099 窗口隔离；
报告选配是单例 id=1，用例间必须恢复默认，防跨用例污染。
"""

import pytest


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    # 恢复报告选配默认 + 清空本组通知
    from infra.db.session import SessionLocal
    from infra.db.repositories import ReportConfigRepo, NotificationRepo
    from model.entity.entities import Notification
    db = SessionLocal()
    try:
        cfg = ReportConfigRepo.get_or_create(db)
        cfg.empty_push_mode = "skip"
        cfg.auto_generate = "disabled"
        cfg.push_channels = ["local"]
        db.commit()
        db.query(Notification).delete()
        db.commit()
    finally:
        db.close()


def _notifications():
    from infra.db.session import SessionLocal
    from model.entity.entities import Notification
    db = SessionLocal()
    try:
        return db.query(Notification).all()
    finally:
        db.close()


def test_default_mode_is_skip():
    from infra.db.session import SessionLocal
    from infra.db.repositories import ReportConfigRepo
    db = SessionLocal()
    try:
        cfg = ReportConfigRepo.get_or_create(db)
        assert cfg.empty_push_mode == "skip"
    finally:
        db.close()


def test_save_mode_alert_only():
    from infra.db.session import SessionLocal
    from infra.db.repositories import ReportConfigRepo
    db = SessionLocal()
    try:
        cfg = ReportConfigRepo.get_or_create(db)
        ReportConfigRepo.save(db, cfg, empty_push_mode="alert_only")
        assert cfg.empty_push_mode == "alert_only"
    finally:
        db.close()


def test_handle_empty_alert_only_creates_notification():
    """alert_only：不推送但产生 ALERT 通知 + 审计"""
    from infra.db.session import SessionLocal
    from infra.db.repositories import ReportConfigRepo, AuditLogRepo
    from app.services.report_service import ReportService
    db = SessionLocal()
    try:
        ReportConfigRepo.save(db, ReportConfigRepo.get_or_create(db), empty_push_mode="alert_only")
    finally:
        db.close()
    ReportService._handle_empty_push("MONTHLY", "2099-01-01 00:00:00", "2099-02-01 00:00:00",
                                    990001, 990001)
    notes = _notifications()
    assert any(n.type == "ALERT" and "EMPTY" in n.title for n in notes), notes


def test_handle_empty_skip_no_notification():
    """skip（默认）：不推送也不通知"""
    from app.services.report_service import ReportService
    ReportService._handle_empty_push("MONTHLY", "2099-01-01 00:00:00", "2099-02-01 00:00:00",
                                    990002, 990002)
    assert _notifications() == []


def test_handle_empty_push_uses_auto_push():
    """push：走自动推送链路（auto_generate=enabled + local 渠道 → PushLog 成功）"""
    from infra.db.session import SessionLocal
    from infra.db.repositories import ReportConfigRepo, PushLogRepo
    from app.services.report_service import ReportService
    from model.entity.entities import ReportVersion, PushLog
    db = SessionLocal()
    try:
        ReportConfigRepo.save(db, ReportConfigRepo.get_or_create(db),
                               empty_push_mode="push", auto_generate="enabled",
                               push_channels=["local"])
        ver = ReportVersion(
            task_id=990003, cycle="MONTHLY",
            window_start="2099-01-01 00:00:00", window_end="2099-02-01 00:00:00",
            version_no=1, version_type="AI_DRAFT", status="DRAFT",
            title="UT-EMPTY-PUSH", content_md="# 空报告", file_path="",
        )
        db.add(ver)
        db.commit()
        db.refresh(ver)
        vid = ver.id
    finally:
        db.close()
    ReportService._handle_empty_push("MONTHLY", "2099-01-01 00:00:00", "2099-02-01 00:00:00",
                                    990003, vid)
    db = SessionLocal()
    try:
        logs = db.query(PushLog).filter(PushLog.version_id == vid).all()
        assert logs and logs[0].status == "SUCCESS", logs
    finally:
        db.close()
