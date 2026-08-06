"""数据源适配器测试 — Syslog/API/DB 三类解析"""
import sys, os
sys.path.insert(0, ".")

import pytest

from capability.adapter.mock_data_gen import ensure_mock_files
from capability.adapter.syslog_adapter import SyslogAdapter
from capability.adapter.api_adapter import ApiAdapter
from capability.adapter.db_adapter import DbAdapter
from capability.adapter.factory import AdapterFactory
from model.entity.entities import DataSourceConfig

WS = "2026-06-01 00:00:00"
WE = "2026-08-01 00:00:00"


def _cfg(type_, file_path):
    return DataSourceConfig(
        name=f"test-{type_.lower()}", type=type_, status="enabled",
        config_json={"file_path": file_path},
    )


def test_mock_files_generated():
    paths = ensure_mock_files()
    for p in paths.values():
        assert os.path.exists(p)
        assert os.path.getsize(p) > 0


def test_syslog_parse_line():
    paths = ensure_mock_files()
    adapter = SyslogAdapter(_cfg("SYSLOG", paths["syslog"]))
    line = "<134>Jul 15 10:23:45 fw-gw brute_force[1234]: Failed password for root from 203.0.113.7 port 54321 ssh2"
    parsed = adapter.parse_line(line, "2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert parsed is not None
    assert parsed["extra"]["event_type"] == "brute_force"
    assert parsed["extra"]["src_ip"] == "203.0.113.7"
    assert parsed["receive_time"] == "2026-07-15 10:23:45"


def test_syslog_fetch():
    paths = ensure_mock_files()
    items = SyslogAdapter(_cfg("SYSLOG", paths["syslog"])).fetch(WS, WE)
    assert len(items) > 100
    assert all(i["source_type"] == "SYSLOG" for i in items)


def test_api_fetch():
    paths = ensure_mock_files()
    items = ApiAdapter(_cfg("API", paths["api"])).fetch(WS, WE)
    assert len(items) > 100
    assert all(i["source_type"] == "API" for i in items)


def test_db_fetch():
    paths = ensure_mock_files()
    items = DbAdapter(_cfg("DB", paths["vuln"])).fetch(WS, WE)
    assert len(items) > 10
    assert all(i["source_type"] == "DB" for i in items)


def test_factory_get():
    paths = ensure_mock_files()
    adapter = AdapterFactory.get(_cfg("SYSLOG", paths["syslog"]))
    assert isinstance(adapter, SyslogAdapter)
    with pytest.raises(ValueError):
        AdapterFactory.get(_cfg("UNKNOWN", ""))
