"""新增数据源适配器测试 — Excel 威胁情报台账 + IOC 情报源"""
import sys, os
sys.path.insert(0, ".")

from capability.adapter.mock_data_gen import ensure_mock_files
from capability.adapter.excel_adapter import ExcelAdapter
from capability.adapter.intel_adapter import IntelAdapter


class _Cfg:
    def __init__(self, stype, cfg):
        self.type = stype
        self.config_json = cfg
        self.name = "t"


def test_excel_adapter_parses_intel_rows():
    paths = ensure_mock_files(force=False)
    adapter = ExcelAdapter(_Cfg("EXCEL", {"file_path": paths["intel"]}))
    rows = adapter.fetch("2025-01-01 00:00:00", "2026-12-31 23:59:59")
    assert len(rows) > 0
    first = rows[0]
    assert first["extra"]["event_type"] == "threat_intel"
    assert first["extra"]["risk_hint"] in ("HIGH", "MEDIUM", "LOW", "INFO")
    assert first["raw_content"]


def test_excel_adapter_filters_by_window():
    paths = ensure_mock_files(force=False)
    adapter = ExcelAdapter(_Cfg("EXCEL", {"file_path": paths["intel"]}))
    # 2000 年窗口应无数据
    rows = adapter.fetch("2000-01-01 00:00:00", "2000-12-31 23:59:59")
    assert rows == []


def test_intel_adapter_parses_iocs():
    paths = ensure_mock_files(force=False)
    adapter = IntelAdapter(_Cfg("INTEL", {"file_path": paths["ioc"]}))
    rows = adapter.fetch("2025-01-01 00:00:00", "2026-12-31 23:59:59")
    assert len(rows) > 0
    first = rows[0]
    assert first["extra"]["event_type"] == "ioc_intel"
    assert first["extra"]["ioc_type"] in ("ip", "domain", "hash")
    assert first["extra"]["risk_hint"] in ("HIGH", "MEDIUM", "LOW")


def test_missing_file_returns_empty():
    adapter = IntelAdapter(_Cfg("INTEL", {"file_path": "/nonexistent/iocs.jsonl"}))
    rows = adapter.fetch("2025-01-01 00:00:00", "2026-12-31 23:59:59")
    assert rows == []
