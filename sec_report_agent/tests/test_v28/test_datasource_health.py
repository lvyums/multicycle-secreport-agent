"""V2.8 #4 数据源健康看板 — 按数据源聚合最近任务拉取统计"""

import pytest


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from infra.db.session import SessionLocal
    from model.entity.entities import ReportTask
    db = SessionLocal()
    try:
        db.query(ReportTask).filter(ReportTask.window_start.like("2098-%")).delete()
        db.commit()
    finally:
        db.close()


def _add_task(stats, status="SUCCESS"):
    from infra.db.session import SessionLocal
    from infra.db.repositories import ReportTaskRepo
    db = SessionLocal()
    try:
        ReportTaskRepo.create(db, cycle="MONTHLY",
                              window_start="2098-01-01 00:00:00",
                              window_end="2098-02-01 00:00:00",
                              status=status, trigger_type="MANUAL",
                              data_source_stats=stats)
    finally:
        db.close()


def test_health_aggregates_ratio(client):
    """es 成功 1 次 + 失败 1 次 → okRatio 0.5 status warning"""
    _add_task({"ut-es": {"ok": True, "count": 10, "type": "API"}})
    _add_task({"ut-es": {"ok": False, "count": 0, "type": "API", "error": "connect timeout"}})
    r = client.get("/api/datasource/health")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    es = [i for i in items if i["name"] == "ut-es"]
    assert es, items
    assert es[0]["totalRuns"] == 2 and es[0]["okRuns"] == 1
    assert es[0]["okRatio"] == 0.5 and es[0]["status"] == "warning"
    assert es[0]["latestError"] == "connect timeout"


def test_health_configured_unknown(client):
    """配置存在但无拉取记录 → unknown"""
    from infra.db.session import SessionLocal
    from infra.db.repositories import DataSourceConfigRepo
    db = SessionLocal()
    try:
        DataSourceConfigRepo.create(db, name="ut-cfg-only", type="API",
                                    status="enabled", config_json={"file_path": "x"})
    finally:
        db.close()
    try:
        r = client.get("/api/datasource/health")
        items = r.json()["data"]["items"]
        item = [i for i in items if i["name"] == "ut-cfg-only"]
        assert item, items
        assert item[0]["status"] == "unknown"
        assert item[0]["totalRuns"] == 0
    finally:
        db2 = SessionLocal()
        try:
            cfg = DataSourceConfigRepo.get_by_name(db2, "ut-cfg-only")
            if cfg:
                DataSourceConfigRepo.delete(db2, cfg)
        finally:
            db2.close()
