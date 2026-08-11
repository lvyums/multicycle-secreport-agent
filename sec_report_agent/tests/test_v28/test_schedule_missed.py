"""V2.8 #3 调度补跑 — 错过窗口检测 + backfill 触发

missed 检测基于真实当前时间往前 3 个窗口；测试库持久，先清对应窗口任务再断言。
"""

import pytest


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    # 恢复测试库：清理 2099 backfill 任务
    from infra.db.session import SessionLocal
    from model.entity.entities import ReportTask
    db = SessionLocal()
    try:
        db.query(ReportTask).filter(ReportTask.cycle == "MONTHLY",
                                    ReportTask.window_start.like("2099-%")).delete()
        db.query(ReportTask).filter(ReportTask.window_start == "2026-06-01 00:00:00").delete()
        db.commit()
    finally:
        db.close()


def _clear_monthly_2026_tasks():
    from infra.db.session import SessionLocal
    from model.entity.entities import ReportTask
    db = SessionLocal()
    try:
        db.query(ReportTask).filter(
            ReportTask.cycle == "MONTHLY",
            ReportTask.window_start.in_(["2026-05-01 00:00:00", "2026-06-01 00:00:00"]),
        ).delete()
        db.commit()
    finally:
        db.close()


def test_missed_detects_gap(client):
    """MONTHLY 缺 2026-06 窗口 → missed 列表含该窗口"""
    _clear_monthly_2026_tasks()
    r = client.get("/api/schedule/missed")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    monthly = [m for m in items if m["cycle"] == "MONTHLY"]
    assert monthly, items
    assert any(m["windowStart"] == "2026-06-01 00:00:00" for m in monthly), monthly


def test_missed_no_gap_after_fill(client):
    """补齐 2026-06 窗口任务后，该窗口不再计入 missed"""
    from infra.db.session import SessionLocal
    from infra.db.repositories import ReportTaskRepo
    _clear_monthly_2026_tasks()
    db = SessionLocal()
    try:
        ReportTaskRepo.create(db, cycle="MONTHLY",
                              window_start="2026-06-01 00:00:00",
                              window_end="2026-07-01 00:00:00",
                              status="SUCCESS", trigger_type="MANUAL")
    finally:
        db.close()
    r = client.get("/api/schedule/missed")
    items = r.json()["data"]["items"]
    monthly = [m for m in items if m["cycle"] == "MONTHLY"]
    assert all(m["windowStart"] != "2026-06-01 00:00:00" for m in monthly), monthly


def test_backfill_calls_generate_with_backfill_flag(client, monkeypatch):
    """backfill 以 trigger_type=BACKFILL + rerun=True 调用生成链路"""
    import asyncio
    from app.services.report_service import ReportService

    captured = {}

    async def fake_generate(cycle, ws, we, trigger_type="MANUAL", rerun=False):
        captured.update(cycle=cycle, ws=ws, we=we, trigger_type=trigger_type, rerun=rerun)
        return {"task_id": 1, "status": "SUCCESS"}

    monkeypatch.setattr(ReportService, "generate", staticmethod(fake_generate))
    r = client.post("/api/schedule/backfill", json={
        "cycle": "MONTHLY", "windowStart": "2099-01-01 00:00:00",
        "windowEnd": "2099-02-01 00:00:00",
    })
    assert r.status_code == 200, r.text
    assert captured == {
        "cycle": "MONTHLY", "ws": "2099-01-01 00:00:00",
        "we": "2099-02-01 00:00:00", "trigger_type": "BACKFILL", "rerun": True,
    }


def test_backfill_missing_window_rejected(client):
    r = client.post("/api/schedule/backfill", json={"cycle": "MONTHLY"})
    assert r.status_code == 200
    assert r.json()["code"] != 0  # 参数错误
