"""V2.6 测试 — 趋势分析 + 报告时间轴（trend_service / /api/trend/*）
用户精简版 8 用例：label 格式、指标扁平化+EMPTY 判定、同窗口去重取最新、
EMPTY 过滤、升序、五周期总览、时间线关联摘要、API 路由可达。

测试数据用 2099 年 WEEKLY 窗口（测试库 SQLite 隔离，不与任何真实窗口冲突）。
"""
import pytest

from app.services.trend_service import TrendService
from infra.db.session import SessionLocal
from model.entity.entities import MetricSnapshot, ReportVersion
from model.enum.enums import ReportCycle

TASK = 990001  # V2.6 测试专用 task_id


def _metrics(alert_total: int, vuln_total: int, event: int) -> dict:
    return {
        "alert": {"total": alert_total, "high": max(0, alert_total // 5), "medium": 0,
                  "low": 0, "info": 0, "close_rate": 0.5, "by_type": {}, "by_day": []},
        "vuln": {"total": vuln_total, "unfixed": vuln_total // 2, "fixed": vuln_total // 2,
                 "ignored": 0, "unfixed_high": max(0, vuln_total // 4), "close_rate": 0.5,
                 "top_assets": []},
        "top": [], "trend": [],
        "raw": {"event_count": event, "vuln_count": vuln_total},
    }


@pytest.fixture()
def trend_data():
    """2099 年 WEEKLY 窗口：A/B 同窗口重跑（取 B）、C 空窗口、D 正常 + 关联版本"""
    db = SessionLocal()
    try:
        # 同窗口两条：A 旧（100）→ B 新（200），验证去重取最新
        a = MetricSnapshot(task_id=TASK, cycle="WEEKLY",
                           window_start="2099-01-05 00:00:00", window_end="2099-01-12 00:00:00",
                           metrics_json=_metrics(100, 10, 100))
        db.add(a)
        db.flush()
        b = MetricSnapshot(task_id=TASK, cycle="WEEKLY",
                           window_start="2099-01-05 00:00:00", window_end="2099-01-12 00:00:00",
                           metrics_json=_metrics(200, 20, 200))
        db.add(b)
        db.flush()
        # 空窗口 C（默认过滤）
        c = MetricSnapshot(task_id=TASK, cycle="WEEKLY",
                           window_start="2099-01-12 00:00:00", window_end="2099-01-19 00:00:00",
                           metrics_json=_metrics(0, 0, 0))
        db.add(c)
        db.flush()
        # 正常窗口 D
        d = MetricSnapshot(task_id=TASK, cycle="WEEKLY",
                           window_start="2099-01-19 00:00:00", window_end="2099-01-26 00:00:00",
                           metrics_json=_metrics(50, 5, 55))
        db.add(d)
        db.flush()
        ver = ReportVersion(task_id=TASK, cycle="WEEKLY",
                            window_start="2099-01-05 00:00:00", window_end="2099-01-12 00:00:00",
                            version_no=1, version_type="AI_DRAFT", status="PUBLISHED",
                            title="V2.6 测试报告", content_md="# t", file_path="",
                            metric_snapshot_id=b.id, operator="ut", remark="v26-test")
        db.add(ver)
        db.commit()
        yield b.id, ver.id
    finally:
        # 清理测试数据
        db.query(MetricSnapshot).filter(MetricSnapshot.task_id == TASK).delete()
        db.query(ReportVersion).filter(ReportVersion.task_id == TASK).delete()
        db.commit()
        db.close()


# ═══════════ 纯函数 ═══════════

def test_window_label_formats():
    """用例1：五周期窗口标签（兼容带时间落库格式）"""
    assert TrendService._window_label("DAILY", "2026-08-11 00:00:00", "2026-08-12 00:00:00") == "08-11"
    assert TrendService._window_label("WEEKLY", "2026-08-03 00:00:00", "2026-08-10 00:00:00") == "08-03~08-10"
    assert TrendService._window_label("MONTHLY", "2026-08-01 00:00:00", "2026-09-01 00:00:00") == "2026-08"
    assert TrendService._window_label("QUARTERLY", "2026-07-01 00:00:00", "2026-10-01 00:00:00") == "2026-07"
    assert TrendService._window_label("YEARLY", "2026-01-01 00:00:00", "2027-01-01 00:00:00") == "2026"
    # 纯日期格式兼容
    assert TrendService._window_label("DAILY", "2026-08-11", "2026-08-11") == "08-11"


def test_parse_metrics_flat_and_empty():
    """用例2：指标扁平化（缺字段兜底）+ EMPTY 判定"""
    flat = TrendService._parse_metrics(_metrics(100, 20, 130))
    assert flat["alertTotal"] == 100 and flat["alertHigh"] == 20
    assert flat["vulnTotal"] == 20 and flat["vulnUnfixedHigh"] == 5
    assert flat["eventCount"] == 130
    # 缺字段/None 兜底
    flat2 = TrendService._parse_metrics({"alert": {}, "vuln": None, "raw": {}})
    assert flat2["alertTotal"] == 0 and flat2["vulnTotal"] == 0 and flat2["eventCount"] == 0
    # EMPTY 判定
    assert TrendService._is_empty(TrendService._parse_metrics(_metrics(0, 0, 0))) is True
    assert TrendService._is_empty(TrendService._parse_metrics(_metrics(1, 0, 1))) is False


# ═══════════ 序列查询（直连测试库） ═══════════

def test_series_dedupe_take_latest(trend_data):
    """用例3：同窗口重跑多条快照 → 只取最新一条"""
    db = SessionLocal()
    try:
        pts = TrendService.list_snapshots(db, "WEEKLY", limit=50)
        hits = [p for p in pts if p["windowStart"].startswith("2099")]
        assert len(hits) == 2                       # B + D（A 被去重、C 被过滤）
        b = next(p for p in hits if p["windowEnd"].startswith("2099-01-12"))
        assert b["alertTotal"] == 200              # 取最新 B，而非旧 A 的 100
        assert b["eventCount"] == 200
    finally:
        db.close()


def test_series_filters_empty(trend_data):
    """用例4：EMPTY 快照默认过滤；include_empty=True 恢复"""
    db = SessionLocal()
    try:
        default = TrendService.list_snapshots(db, "WEEKLY", limit=50)
        assert not any(p["windowStart"].startswith("2099-01-12") for p in default)
        incl = TrendService.list_snapshots(db, "WEEKLY", limit=50, include_empty=True)
        empty = [p for p in incl if p["windowStart"].startswith("2099-01-12")]
        assert len(empty) == 1 and empty[0]["alertTotal"] == 0
    finally:
        db.close()


def test_series_ascending_order(trend_data):
    """用例5：序列按 window_end 升序（时间轴从左到右）"""
    db = SessionLocal()
    try:
        pts = TrendService.list_snapshots(db, "WEEKLY", limit=50)
        hits = [p for p in pts if p["windowStart"].startswith("2099")]
        assert [p["windowEnd"] for p in hits] == sorted(p["windowEnd"] for p in hits)
    finally:
        db.close()


def test_all_cycles_returns_five():
    """用例6：五周期总览各返回序列"""
    db = SessionLocal()
    try:
        series_list = TrendService.all_cycles(db, limit=5)
        assert [s["cycle"] for s in series_list] == [c.value for c in ReportCycle]
        for s in series_list:
            assert s["cycleLabel"]  # 中文标签非空
    finally:
        db.close()


def test_timeline_joins_snapshot(trend_data):
    """用例7：时间线版本 × 指标摘要（metric_snapshot_id 关联）"""
    db = SessionLocal()
    try:
        tl = TrendService.timeline(db, cycle="WEEKLY", limit=100)
        item = next(i for i in tl["items"] if i["title"] == "V2.6 测试报告")
        assert item["alertTotal"] == 200            # 来自 B 快照
        assert item["alertHigh"] == 40
        assert item["vulnTotal"] == 20
        assert item["status"] == "PUBLISHED"
        assert item["windowStart"] == "2099-01-05 00:00:00"
    finally:
        db.close()


# ═══════════ API ═══════════

def test_trend_api_routes(client, trend_data):
    """用例8：/api/trend/* 路由可达（conftest 注入 admin，无需 token）"""
    r = client.get("/api/trend/series", params={"cycle": "WEEKLY", "limit": 50})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert body["data"]["cycle"] == "WEEKLY"

    r2 = client.get("/api/trend/timeline", params={"cycle": "WEEKLY", "limit": 100})
    assert r2.status_code == 200 and r2.json()["code"] == 0
    titles = [i["title"] for i in r2.json()["data"]["items"]]
    assert "V2.6 测试报告" in titles

    r3 = client.get("/api/trend/all-cycles", params={"limit": 5})
    assert r3.status_code == 200 and r3.json()["code"] == 0
    assert len(r3.json()["data"]["items"]) == 5
