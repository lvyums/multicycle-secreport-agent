"""指标聚合测试 — 固定输入断言精确值（防幻觉核心）"""
import sys
sys.path.insert(0, ".")

from capability.metric.aggregator import MetricAggregator
from model.struct.structs import StdEvent


def _evt(event_type: str, risk: str, status: str = "open", day: int = 15,
         src="1.1.1.1", asset="10.0.0.1"):
    return StdEvent(
        event_time=f"2026-07-{day:02d} 10:00:00", source_type="SYSLOG",
        event_type=event_type, risk_level=risk, status=status,
        src_ip=src, asset_ip=asset,
    )


def _vuln(risk: str, status: str, asset: str = "10.0.0.1"):
    return StdEvent(
        event_time="2026-07-15 10:00:00", source_type="DB",
        event_type="vuln", risk_level=risk, status=status, asset_ip=asset,
    )


def test_alert_total_and_levels():
    events = [
        _evt("brute_force", "HIGH"), _evt("brute_force", "HIGH"),
        _evt("web_attack", "MEDIUM"), _evt("dos", "LOW"),
    ]
    agg = MetricAggregator("MONTHLY")
    m = agg.build(events, [], "2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert m.alert["total"] == 4
    assert m.alert["high"] == 2
    assert m.alert["medium"] == 1
    assert m.alert["low"] == 1
    assert m.alert["by_type"]["brute_force"] == 2


def test_alert_close_rate_decimal():
    events = [_evt("brute_force", "HIGH", status="closed"), _evt("dos", "LOW", status="open")]
    m = MetricAggregator("MONTHLY").build(events, [], "2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert m.alert["close_rate"] == 0.5


def test_vuln_metrics():
    vulns = [
        _vuln("HIGH", "unfixed"), _vuln("LOW", "fixed"),
        _vuln("HIGH", "unfixed", asset="10.0.0.2"),
    ]
    m = MetricAggregator("MONTHLY").build([], vulns, "2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert m.vuln["total"] == 3
    assert m.vuln["unfixed"] == 2
    assert m.vuln["unfixed_high"] == 2
    assert m.vuln["close_rate"] == round(1 / 3, 4)
    assert len(m.vuln["top_assets"]) == 2


def test_top_rankings():
    events = [
        _evt("brute_force", "HIGH", src="203.0.113.1", day=1),
        _evt("brute_force", "HIGH", src="203.0.113.1", day=2),
        _evt("web_attack", "MEDIUM", src="203.0.113.2", day=3),
        _evt("malware", "HIGH", src="203.0.113.2", day=4),
    ]
    m = MetricAggregator("MONTHLY").build(events, [], "2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert m.top["top_src"][0]["ip"] == "203.0.113.1"
    assert m.top["top_src"][0]["count"] == 2
    assert m.top["top_type"][0]["type"] == "brute_force"


def test_trend_by_day():
    events = [_evt("dos", "LOW", day=1), _evt("dos", "LOW", day=1), _evt("dos", "LOW", day=2)]
    m = MetricAggregator("MONTHLY").build(events, [], "2026-07-01 00:00:00", "2026-08-01 00:00:00")
    days = m.trend["by_day"]
    assert len(days) == 2
    assert days[0]["total"] == 2
    assert days[1]["total"] == 1
    assert days[0]["date"] == "2026-07-01"


def test_empty_input():
    m = MetricAggregator("MONTHLY").build([], [], "2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert m.alert["total"] == 0
    assert m.raw["event_count"] == 0
