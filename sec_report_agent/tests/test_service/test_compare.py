"""环比对比测试 — 本期 vs 上期增量/百分比计算"""
import sys
sys.path.insert(0, ".")

from app.services.report_service import ReportService


def test_build_compare_normal():
    prev = {"alert": {"total": 100, "high": 10, "close_rate": 0.5},
            "vuln": {"unfixed_high": 3}}
    cur = {"alert": {"total": 150, "high": 15, "close_rate": 0.6},
           "vuln": {"unfixed_high": 5}}
    c = ReportService._build_compare(prev, cur)
    assert c["alert_total"]["cur"] == 150
    assert c["alert_total"]["prev"] == 100
    assert "+50" in c["alert_total"]["delta"]
    assert "+50.0%" in c["alert_total"]["delta"]
    assert c["alert_high"]["delta"].startswith("15（+5 / +50.0%）")
    assert "60.0%（+10.0pp" in c["close_rate"]["delta"]
    assert c["unfixed_high"]["delta"].startswith("5（+2 / +66.7%）")


def test_build_compare_prev_zero():
    prev = {"alert": {"total": 0, "high": 0, "close_rate": 0},
            "vuln": {"unfixed_high": 0}}
    cur = {"alert": {"total": 10, "high": 2, "close_rate": 0.1},
           "vuln": {"unfixed_high": 1}}
    c = ReportService._build_compare(prev, cur)
    assert c["alert_total"]["delta"] == "10（无上期）"
    assert c["close_rate"]["delta"] == "10.0%（无上期）"


def test_build_compare_decrease():
    prev = {"alert": {"total": 200, "high": 50, "close_rate": 0.8},
            "vuln": {"unfixed_high": 4}}
    cur = {"alert": {"total": 150, "high": 40, "close_rate": 0.75},
           "vuln": {"unfixed_high": 2}}
    c = ReportService._build_compare(prev, cur)
    assert "-50" in c["alert_total"]["delta"]
    assert "-25.0%" in c["alert_total"]["delta"]
    assert "75.0%（-5.0pp" in c["close_rate"]["delta"]
    assert "-50.0%" in c["unfixed_high"]["delta"]


def test_build_compare_missing_groups():
    c = ReportService._build_compare({}, {})
    assert c["alert_total"]["cur"] == 0
    assert c["alert_total"]["delta"] == "0"
