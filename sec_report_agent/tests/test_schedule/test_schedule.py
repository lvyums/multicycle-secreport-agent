"""调度测试 — cron 解析 / 窗口计算 / 下次触发"""
import sys
sys.path.insert(0, ".")

from datetime import datetime

import pytest

from infra.schedule.simple_scheduler import parse_cron, SimpleScheduler
from app.tasks.report_task import calc_window


def test_parse_cron_basic():
    cron = parse_cron("0 2 1 * *")
    assert 0 in cron[0] and 2 in cron[1] and 1 in cron[2]
    assert cron[3] == set() and cron[4] == set()


def test_parse_cron_list_and_range():
    cron = parse_cron("30 1,13 * * 1-5")
    assert 30 in cron[0]
    assert {1, 13} == cron[1]
    assert {1, 2, 3, 4, 5} == cron[4]


def test_parse_cron_invalid():
    with pytest.raises(ValueError):
        parse_cron("0 2 1")  # 非 5 字段


def test_calc_window_monthly():
    ws, we = calc_window("MONTHLY", ref=datetime(2026, 8, 6))
    assert ws == "2026-07-01 00:00:00"
    assert we == "2026-08-01 00:00:00"


def test_calc_window_daily():
    ws, we = calc_window("DAILY", ref=datetime(2026, 8, 6))
    assert ws == "2026-08-05 00:00:00"
    assert we == "2026-08-06 00:00:00"


def test_calc_window_yearly():
    # 年报统计上一自然年（前闭后开）
    ws, we = calc_window("YEARLY", ref=datetime(2026, 8, 6))
    assert ws == "2025-01-01 00:00:00"
    assert we == "2026-01-01 00:00:00"


def test_scheduler_next_run_daily():
    s = SimpleScheduler()
    s.add_cron_job("test", "0 1 * * *", lambda: None)
    nxt = s.get_next_run_time("test")
    assert nxt is not None
    assert nxt.endswith("01:00:00")
