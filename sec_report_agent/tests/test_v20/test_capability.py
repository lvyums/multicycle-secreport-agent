"""capability 层覆盖率测试（V2.0）

覆盖: adapter / rag / render / judge / metric / clean / push 全部模块,
目标: capability 层各文件覆盖率 ≥ 70%。

运行: cd sec_report_agent && python3 -m pytest tests/test_v20/ -q
"""
import sys
sys.path.insert(0, ".")

import csv
import json
import os

import pytest


def _ensure_logger_shim():
    """common.logger 包级 LogManager 垫片:
    infra.vector.vector_store 使用 `from common.logger import LogManager`,
    而 common.logger/__init__.py 未导出该符号; 在测试进程内补挂载,
    使 capability.rag 相关模块可导入（不改业务代码）。
    """
    import common.logger as cl
    if not hasattr(cl, "LogManager"):
        try:
            from common.logger.logger import LogManager
            cl.LogManager = LogManager
        except Exception:
            pass


_ensure_logger_shim()


# ═══════════════════════════════════════════════════════════════
# 公共工具
# ═══════════════════════════════════════════════════════════════

def _ds_config(stype: str, config_json: dict, name: str = "ut-src"):
    """构造 DataSourceConfig ORM 实例（无需 DB 会话）"""
    from model.entity.entities import DataSourceConfig
    return DataSourceConfig(name=name, type=stype, status="enabled",
                            config_json=config_json)


def _std_event(event_time="2026-07-15 10:23:45", source_type="API",
               event_type="brute_force", risk_level="HIGH", asset_ip="10.0.1.5",
               src_ip="203.0.113.9", status="closed", device_source="fw-gw",
               raw_content="raw", extra=None):
    from model.struct.structs import StdEvent
    return StdEvent(event_time=event_time, source_type=source_type,
                    event_type=event_type, risk_level=risk_level,
                    asset_ip=asset_ip, src_ip=src_ip, status=status,
                    device_source=device_source, raw_content=raw_content,
                    extra=extra or {})


def _metric(alert=None, vuln=None, top=None, trend=None, cycle="DAILY",
            ws="2026-07-01 00:00:00", we="2026-07-02 00:00:00"):
    from model.struct.structs import MetricSet
    return MetricSet(cycle=cycle, window_start=ws, window_end=we,
                     alert=alert or {}, vuln=vuln or {}, top=top or {},
                     trend=trend or {}, raw={"event_count": 1, "vuln_count": 1})


# ═══════════════════════════════════════════════════════════════
# A. adapter_base
# ═══════════════════════════════════════════════════════════════

class _ConcreteAdapter:
    """不依赖 adapter_base 的轻量替身（用于基类方法测试的宿主）"""

    def __init__(self, config):
        from capability.adapter.adapter_base import DataSourceAdapter
        self._base = DataSourceAdapter.__new__(DataSourceAdapter)
        DataSourceAdapter.__init__(self._base, config)

    def __getattr__(self, item):
        return getattr(self._base, item)


class _BadConfigAdapter(_ConcreteAdapter):
    pass


def _make_concrete(config):
    from capability.adapter.adapter_base import DataSourceAdapter
    class _T(DataSourceAdapter):
        type = "TEST_SRC"

        def fetch(self, window_start, window_end, task_id=0):
            return []

    return _T(config)


def test_adapter_base_init_and_name():
    adapter = _make_concrete(_ds_config("TEST_SRC", {}))
    assert adapter.name == "ut-src"
    assert adapter.config is not None
    assert adapter.type == "TEST_SRC"


def test_adapter_base_validate_config_default_empty():
    adapter = _make_concrete(_ds_config("TEST_SRC", {}))
    assert adapter.validate_config() == []


def test_adapter_base_test_connection_ok():
    adapter = _make_concrete(_ds_config("TEST_SRC", {}))
    ok, msg = adapter.test_connection()
    assert ok is True
    assert msg == "ok"


def test_adapter_base_test_connection_fail():
    from capability.adapter.adapter_base import DataSourceAdapter

    class _Invalid(DataSourceAdapter):
        type = "INVALID"

        def fetch(self, window_start, window_end, task_id=0):
            return []

        def validate_config(self):
            return ["缺少 file_path 配置", "缺少 token"]

    adapter = _Invalid(_ds_config("INVALID", {}))
    ok, msg = adapter.test_connection()
    assert ok is False
    assert "缺少 file_path 配置" in msg
    assert "缺少 token" in msg


def test_adapter_base_get_type_label():
    adapter = _make_concrete(_ds_config("API", {}))
    adapter.type = "API"
    assert adapter.get_type_label() == "告警平台"
    # 未注册类型 → 原样返回
    adapter.type = "BOGUS"
    assert adapter.get_type_label() == "BOGUS"


def test_adapter_base_describe():
    adapter = _make_concrete(_ds_config("SYSLOG", {"file_path": "/tmp/x.log"}))
    info = adapter.describe()
    assert info["name"] == "ut-src"
    assert info["type"] == "TEST_SRC"
    assert info["type_label"] == "TEST_SRC"
    assert info["config"] == {"file_path": "/tmp/x.log"}
    assert info["status"] == "enabled"


def test_adapter_base_fetch_abstract():
    from capability.adapter.adapter_base import DataSourceAdapter
    with pytest.raises(TypeError):
        DataSourceAdapter(_ds_config("X", {}))


# ═══════════════════════════════════════════════════════════════
# B. api_adapter
# ═══════════════════════════════════════════════════════════════

def test_api_validate_config(tmp_path):
    from capability.adapter.api_adapter import ApiAdapter
    # 空配置（既无 endpoint 也无 file_path）
    a1 = ApiAdapter(_ds_config("API", {}))
    assert "缺少" in a1.validate_config()[0]
    # 文件不存在
    a2 = ApiAdapter(_ds_config("API", {"file_path": "/nonexistent/x.jsonl"}))
    assert any("不存在" in e for e in a2.validate_config())
    # 合法文件
    f = tmp_path / "alerts.jsonl"
    f.write_text("", encoding="utf-8")
    a3 = ApiAdapter(_ds_config("API", {"file_path": str(f)}))
    assert a3.validate_config() == []
    # HTTP 模式: 缺 endpoint
    a4 = ApiAdapter(_ds_config("API", {"auth_type": "bearer", "token": "x"}))
    assert any("endpoint" in e for e in a4.validate_config())
    # HTTP 模式: basic 缺账号
    a5 = ApiAdapter(_ds_config("API", {"endpoint": "http://x/alerts", "auth_type": "basic"}))
    assert any("username/password" in e for e in a5.validate_config())


def test_api_fetch_missing_file():
    from capability.adapter.api_adapter import ApiAdapter
    adapter = ApiAdapter(_ds_config("API", {"file_path": "/nonexistent/a.jsonl"}))
    assert adapter.fetch("2026-01-01 00:00:00", "2026-12-31 23:59:59") == []


def test_api_fetch_parses_and_filters(tmp_path):
    from capability.adapter.api_adapter import ApiAdapter
    f = tmp_path / "alerts.jsonl"
    f.write_text("\n".join([
        json.dumps({"id": "AL-1", "time": "2026-07-10 10:00:00", "severity": "CRITICAL",
                    "event_type": "brute_force", "src_ip": "1.1.1.1", "dst_ip": "10.0.0.2",
                    "device": "fw", "rule_id": "R-1", "status": "open"}),
        "this is not json",
        json.dumps({"id": "AL-2", "time": "2020-01-01 00:00:00", "severity": "LOW"}),
        json.dumps({"id": "AL-3", "time": "2026-07-11 11:00:00"}),  # 无 severity
    ]), encoding="utf-8")
    adapter = ApiAdapter(_ds_config("API", {"file_path": str(f)}))
    items = adapter.fetch("2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert len(items) == 2
    first = items[0]
    assert first["source_type"] == "API"
    assert first["status"] == "OK"
    assert first["extra"]["risk_hint"] == "HIGH"          # CRITICAL → HIGH
    assert first["extra"]["event_type"] == "brute_force"
    assert first["extra"]["alert_id"] == "AL-1"
    # 无 severity → INFO
    assert items[1]["extra"]["risk_hint"] == "INFO"


def test_api_parse_item():
    from capability.adapter.api_adapter import ApiAdapter
    adapter = ApiAdapter(_ds_config("API", {"file_path": "/x.jsonl"}))
    ws, we = "2026-07-01 00:00:00", "2026-08-01 00:00:00"
    # 窗口内
    parsed = adapter.parse_item({"time": "2026-07-10 10:00:00", "severity": "UNKNOWN",
                                 "alert_name": "fallback-name"}, ws, we)
    assert parsed is not None
    assert parsed["extra"]["risk_hint"] == "LOW"          # 未知 severity 兜底
    assert parsed["extra"]["event_type"] == "fallback-name"
    # 无时间 → 丢弃
    assert adapter.parse_item({"severity": "HIGH"}, ws, we) is None
    # 窗口外 → 丢弃
    assert adapter.parse_item({"time": "2025-01-01 00:00:00"}, ws, we) is None


# ═══════════════════════════════════════════════════════════════
# C. db_adapter
# ═══════════════════════════════════════════════════════════════

def _write_vuln_csv(path, rows, header=None):
    header = header or ["asset_ip", "asset_name", "vuln_name", "cvss",
                        "risk_level", "status", "discover_time", "source_name"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def test_db_validate_config(tmp_path):
    from capability.adapter.db_adapter import DbAdapter
    assert "缺少" in DbAdapter(_ds_config("DB", {})).validate_config()[0]
    assert any("不存在" in e for e in
               DbAdapter(_ds_config("DB", {"file_path": "/nope.csv"})).validate_config())
    f = tmp_path / "v.csv"
    f.write_text("", encoding="utf-8")
    assert DbAdapter(_ds_config("DB", {"file_path": str(f)})).validate_config() == []
    # db 模式: 缺 table
    assert any("table" in e for e in
               DbAdapter(_ds_config("DB", {"db_url": "sqlite:///:memory:"})).validate_config())


def test_db_fetch_missing_file():
    from capability.adapter.db_adapter import DbAdapter
    adapter = DbAdapter(_ds_config("DB", {"file_path": "/nope.csv"}))
    assert adapter.fetch("2026-01-01 00:00:00", "2026-12-31 23:59:59") == []


def test_db_fetch_rows(tmp_path):
    from capability.adapter.db_adapter import DbAdapter
    f = tmp_path / "vulns.csv"
    _write_vuln_csv(f, [
        {"asset_ip": "10.0.1.1", "asset_name": "srv-1", "vuln_name": "Log4j",
         "cvss": "9.8", "risk_level": "high", "status": "unfixed",
         "discover_time": "2026-07-05", "source_name": "nessus"},
        {"asset_ip": "10.0.1.2", "asset_name": "srv-2", "vuln_name": "Redis",
         "cvss": "5.0", "risk_level": "medium", "status": "fixed",
         "discover_time": "2026-07-06", "source_name": "nessus"},
    ])
    adapter = DbAdapter(_ds_config("DB", {"file_path": str(f)}))
    items = adapter.fetch("2026-01-01 00:00:00", "2026-12-31 23:59:59")
    assert len(items) == 2
    first = items[0]
    assert first["source_type"] == "DB"
    assert first["extra"]["event_type"] == "vuln"
    assert first["extra"]["risk_hint"] == "HIGH"          # upper 化
    assert first["extra"]["cvss"] == 9.8
    assert first["receive_time"] == "2026-07-05"
    assert "vuln_name=Log4j" in first["raw_content"]
    assert first["extra"]["vuln_status"] == "unfixed"


def test_db_fetch_header_only(tmp_path):
    from capability.adapter.db_adapter import DbAdapter
    f = tmp_path / "empty.csv"
    _write_vuln_csv(f, [])
    adapter = DbAdapter(_ds_config("DB", {"file_path": str(f)}))
    assert adapter.fetch("2026-01-01 00:00:00", "2026-12-31 23:59:59") == []


# ═══════════════════════════════════════════════════════════════
# D. excel_adapter
# ═══════════════════════════════════════════════════════════════

def _write_intel_xlsx(path, rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "情报"
    header = ["情报名称", "情报类型", "影响资产", "置信度", "发布时间", "来源", "处置建议"]
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(str(path))


def test_excel_validate_config(tmp_path):
    from capability.adapter.excel_adapter import ExcelAdapter
    assert ExcelAdapter(_ds_config("EXCEL", {})).validate_config() == ["缺少 file_path 配置"]
    assert any("不存在" in e for e in
               ExcelAdapter(_ds_config("EXCEL", {"file_path": "/nope.xlsx"})).validate_config())
    f = tmp_path / "a.xlsx"
    _write_intel_xlsx(f, [])
    assert ExcelAdapter(_ds_config("EXCEL", {"file_path": str(f)})).validate_config() == []


def test_excel_fetch_missing_file():
    from capability.adapter.excel_adapter import ExcelAdapter
    adapter = ExcelAdapter(_ds_config("EXCEL", {"file_path": "/nope.xlsx"}))
    assert adapter.fetch("2026-01-01 00:00:00", "2026-12-31 23:59:59") == []


def test_excel_fetch_corrupt_file(tmp_path):
    from capability.adapter.excel_adapter import ExcelAdapter
    f = tmp_path / "bad.xlsx"
    f.write_bytes(b"\x00\x01garbage-not-xlsx")
    adapter = ExcelAdapter(_ds_config("EXCEL", {"file_path": str(f)}))
    assert adapter.fetch("2026-01-01 00:00:00", "2026-12-31 23:59:59") == []


def test_excel_fetch_rows(tmp_path):
    from capability.adapter.excel_adapter import ExcelAdapter
    f = tmp_path / "intel.xlsx"
    _write_intel_xlsx(f, [
        ["勒索软件通报-001", "勒索软件", "10.0.1.1", "高", "2026-07-10 10:00:00",
         "微步在线", "封禁IOC"],
        ["APT通报-002", "APT组织", "10.0.1.2", "中", "2026-07-11 11:00:00",
         "奇安信", "升级补丁"],
        ["过期通报", "钓鱼", "10.0.1.3", "低", "2020-01-01 00:00:00",
         "OTX", "隔离主机"],          # 窗口外
        [None, None, None, None, None, None, None],        # 空行
    ])
    adapter = ExcelAdapter(_ds_config("EXCEL", {"file_path": str(f)}))
    items = adapter.fetch("2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert len(items) == 2
    first = items[0]
    assert first["source_type"] == "EXCEL"
    assert first["extra"]["event_type"] == "threat_intel"
    assert first["extra"]["risk_hint"] == "MEDIUM"        # 高置信度 → MEDIUM
    assert first["extra"]["intel_name"] == "勒索软件通报-001"
    assert first["extra"]["device"] == "threat-intel"
    assert items[1]["extra"]["risk_hint"] == "LOW"         # 中置信度 → LOW


def test_excel_parse_row_direct():
    from capability.adapter.excel_adapter import ExcelAdapter
    adapter = ExcelAdapter(_ds_config("EXCEL", {"file_path": "/x.xlsx"}))
    ws, we = "2026-07-01 00:00:00", "2026-08-01 00:00:00"
    row = {"发布时间": "2026-07-20 08:00:00", "置信度": "低", "影响资产": "10.0.0.9",
           "情报名称": "n", "情报类型": "t", "来源": "s", "处置建议": "a"}
    parsed = adapter.parse_row(row, ws, we)
    assert parsed is not None
    assert parsed["extra"]["risk_hint"] == "INFO"          # 低置信度 → INFO
    # 未知置信度 → LOW
    row["置信度"] = "unk"
    assert adapter.parse_row(row, ws, we)["extra"]["risk_hint"] == "LOW"
    # 无时间 → None
    assert adapter.parse_row({"发布时间": ""}, ws, we) is None
    # 窗口外 → None
    assert adapter.parse_row({"发布时间": "2025-01-01 00:00:00"}, ws, we) is None


# ═══════════════════════════════════════════════════════════════
# E. syslog_adapter
# ═══════════════════════════════════════════════════════════════

def test_syslog_validate_config(tmp_path):
    from capability.adapter.syslog_adapter import SyslogAdapter
    assert SyslogAdapter(_ds_config("SYSLOG", {})).validate_config() == ["缺少 file_path 配置"]
    assert any("不存在" in e for e in
               SyslogAdapter(_ds_config("SYSLOG", {"file_path": "/nope.log"})).validate_config())
    f = tmp_path / "x.log"
    f.write_text("", encoding="utf-8")
    assert SyslogAdapter(_ds_config("SYSLOG", {"file_path": str(f)})).validate_config() == []


def test_syslog_fetch_missing_file():
    from capability.adapter.syslog_adapter import SyslogAdapter
    adapter = SyslogAdapter(_ds_config("SYSLOG", {"file_path": "/nope.log"}))
    assert adapter.fetch("2026-01-01 00:00:00", "2026-12-31 23:59:59") == []


def test_syslog_fetch_parses(tmp_path):
    from capability.adapter.syslog_adapter import SyslogAdapter
    f = tmp_path / "syslog.log"
    f.write_text("\n".join([
        "<134>Jul 15 10:23:45 fw-gw brute_force[1234]: Failed password for root from 203.0.113.7 port 54321 ssh2",
        "<165>Jul 15 10:24:00 waf-01 web_attack[88]: WAF blocked SQLi from 8.8.8.8",
        "garbage line not syslog",
        "",
        "<134>Jan 01 00:00:00 core-sw dos[1]: Flood detected: 9.9.9.9 -> 10.0.0.1 100 pps",
    ]), encoding="utf-8")
    adapter = SyslogAdapter(_ds_config("SYSLOG", {"file_path": str(f)}))
    items = adapter.fetch("2026-07-01 00:00:00", "2026-07-31 23:59:59")
    assert len(items) == 2
    first = items[0]
    assert first["source_type"] == "SYSLOG"
    assert first["extra"]["event_type"] == "brute_force"
    assert first["extra"]["risk_hint"] == "HIGH"          # Failed password 关键词
    assert first["extra"]["src_ip"] == "203.0.113.7"
    assert first["extra"]["priority"] == "134"
    assert first["extra"]["pid"] == "1234"
    # Jan 01 在窗口外被过滤
    assert all(i["receive_time"] >= "2026-07-01" for i in items)


def test_syslog_parse_line_edges():
    from capability.adapter.syslog_adapter import SyslogAdapter
    adapter = SyslogAdapter(_ds_config("SYSLOG", {"file_path": "/x.log"}))
    ws, we = "2026-07-01 00:00:00", "2026-07-31 23:59:59"
    # 不匹配
    assert adapter.parse_line("hello world", ws, we) is None
    # 非法月份 → None
    assert adapter.parse_line("<134>Xxx 15 10:23:45 host proc[1]: msg", ws, we) is None
    # 窗口外 → None
    assert adapter.parse_line("<134>Jan 01 10:00:00 host proc[1]: msg", ws, we) is None
    # 内网主机 → asset_ip 填 host
    parsed = adapter.parse_line("<134>Jul 15 10:23:45 10.0.0.1 sshd[5]: Malware detected", ws, we)
    assert parsed["extra"]["asset_ip"] == "10.0.0.1"
    assert parsed["extra"]["risk_hint"] == "HIGH"
    # 外网主机 → asset_ip 空
    parsed2 = adapter.parse_line("<134>Jul 15 10:23:45 fw-gw sshd[5]: Policy violation on 10.0.0.2", ws, we)
    assert parsed2["extra"]["asset_ip"] == ""
    assert parsed2["extra"]["risk_hint"] == "LOW"
    # 无 IP → src_ip 空
    parsed3 = adapter.parse_line("<134>Jul 15 10:23:45 fw-gw sshd[5]: no ip here", ws, we)
    assert parsed3["extra"]["src_ip"] == ""
    assert parsed3["extra"]["risk_hint"] == "INFO"


def test_syslog_extract_ip():
    from capability.adapter.syslog_adapter import SyslogAdapter
    assert SyslogAdapter._extract_ip("from 1.2.3.4 port 22") == "1.2.3.4"
    assert SyslogAdapter._extract_ip("no ip") == ""


# ═══════════════════════════════════════════════════════════════
# F. intel_adapter
# ═══════════════════════════════════════════════════════════════

def test_intel_validate_config(tmp_path):
    from capability.adapter.intel_adapter import IntelAdapter
    assert IntelAdapter(_ds_config("INTEL", {})).validate_config() == ["缺少 file_path 配置"]
    assert any("不存在" in e for e in
               IntelAdapter(_ds_config("INTEL", {"file_path": "/nope.jsonl"})).validate_config())
    f = tmp_path / "i.jsonl"
    f.write_text("", encoding="utf-8")
    assert IntelAdapter(_ds_config("INTEL", {"file_path": str(f)})).validate_config() == []


def test_intel_fetch_missing_file():
    from capability.adapter.intel_adapter import IntelAdapter
    adapter = IntelAdapter(_ds_config("INTEL", {"file_path": "/nope.jsonl"}))
    assert adapter.fetch("2026-01-01 00:00:00", "2026-12-31 23:59:59") == []


def test_intel_fetch_parses(tmp_path):
    from capability.adapter.intel_adapter import IntelAdapter
    f = tmp_path / "iocs.jsonl"
    f.write_text("\n".join([
        json.dumps({"ioc_type": "ip", "ioc_value": "203.0.113.66", "confidence": "high",
                    "source": "微步", "first_seen": "2026-07-10 08:00:00",
                    "tags": ["apt", "malware"]}),
        "bad json",
        json.dumps({"ioc_type": "domain", "ioc_value": "evil.example.org", "confidence": "low",
                    "source": "OTX", "first_seen": "2020-01-01 00:00:00"}),  # 窗口外
    ]), encoding="utf-8")
    adapter = IntelAdapter(_ds_config("INTEL", {"file_path": str(f)}))
    items = adapter.fetch("2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert len(items) == 1
    first = items[0]
    assert first["extra"]["event_type"] == "ioc_intel"
    assert first["extra"]["risk_hint"] == "HIGH"
    assert first["extra"]["src_ip"] == "203.0.113.66"      # ioc_type=ip → src_ip
    assert first["extra"]["tags"] == ["apt", "malware"]


def test_intel_parse_item_direct():
    from capability.adapter.intel_adapter import IntelAdapter
    adapter = IntelAdapter(_ds_config("INTEL", {"file_path": "/x.jsonl"}))
    ws, we = "2026-07-01 00:00:00", "2026-08-01 00:00:00"
    # 未知置信度 → LOW
    parsed = adapter.parse_item({"first_seen": "2026-07-10 00:00:00",
                                 "confidence": "critical"}, ws, we)
    assert parsed["extra"]["risk_hint"] == "LOW"
    # domain 类型不填 src_ip
    parsed2 = adapter.parse_item({"first_seen": "2026-07-10 00:00:00",
                                  "ioc_type": "domain", "ioc_value": "d.com"}, ws, we)
    assert parsed2["extra"]["src_ip"] == ""
    # 无时间 → None
    assert adapter.parse_item({}, ws, we) is None


# ═══════════════════════════════════════════════════════════════
# G. history_adapter
# ═══════════════════════════════════════════════════════════════

@pytest.fixture()
def _hist_session(monkeypatch):
    """内存 SQLite + 替换 infra.db.session.SessionLocal

    history_adapter.fetch 内 `from infra.db.session import SessionLocal`
    是调用期导入, 因此 patch 模块属性即可生效。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from infra.db.base import Base
    import model.entity.entities  # noqa: F401  注册实体
    import infra.db.session as dbsession

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(dbsession, "SessionLocal", TestingSession)
    return TestingSession


def test_history_adapter_returns_prev_snapshot(_hist_session):
    from infra.db.repositories import MetricSnapshotRepo
    from capability.adapter.history_adapter import HistoryAdapter

    db = _hist_session()
    MetricSnapshotRepo.create(db, task_id=1, cycle="MONTHLY",
                              window_start="2026-06-01 00:00:00",
                              window_end="2026-07-01 00:00:00",
                              metrics_json={"alert": {"total": 9, "high": 2}})
    db.close()

    adapter = HistoryAdapter(_ds_config("HISTORY", {"cycle": "MONTHLY"}))
    adapter.current_cycle = "MONTHLY"
    items = adapter.fetch("2026-07-01 00:00:00", "2026-08-01 00:00:00")
    assert len(items) == 1
    ev = items[0]
    assert ev["source_type"] == "HISTORY"
    assert ev["extra"]["event_type"] == "history_metric"
    assert ev["extra"]["prev_metrics"]["alert"]["total"] == 9
    assert ev["extra"]["prev_window"] == "2026-06-01 00:00:00~2026-07-01 00:00:00"


def test_history_adapter_no_prev(_hist_session):
    from capability.adapter.history_adapter import HistoryAdapter
    adapter = HistoryAdapter(_ds_config("HISTORY", {"cycle": "MONTHLY"}))
    adapter.current_cycle = "MONTHLY"
    assert adapter.fetch("2026-07-01 00:00:00", "2026-08-01 00:00:00") == []


def test_history_adapter_cycle_from_config(_hist_session):
    from infra.db.repositories import MetricSnapshotRepo
    from capability.adapter.history_adapter import HistoryAdapter

    db = _hist_session()
    MetricSnapshotRepo.create(db, task_id=2, cycle="WEEKLY",
                              window_start="2026-07-01 00:00:00",
                              window_end="2026-07-08 00:00:00",
                              metrics_json={"alert": {"total": 3}})
    db.close()

    # 无 current_cycle，从 config_json 取 cycle
    adapter = HistoryAdapter(_ds_config("HISTORY", {"cycle": "WEEKLY"}))
    items = adapter.fetch("2026-07-08 00:00:00", "2026-07-15 00:00:00")
    assert len(items) == 1


def test_history_adapter_no_cycle_no_data(_hist_session):
    from capability.adapter.history_adapter import HistoryAdapter
    adapter = HistoryAdapter(_ds_config("HISTORY", {}))
    assert adapter.fetch("2026-07-01 00:00:00", "2026-08-01 00:00:00") == []


# ═══════════════════════════════════════════════════════════════
# H. adapter factory
# ═══════════════════════════════════════════════════════════════

def test_adapter_factory_register_get(monkeypatch):
    from capability.adapter.factory import AdapterFactory
    from capability.adapter.adapter_base import DataSourceAdapter

    class _TmpAdapter(DataSourceAdapter):
        type = "TMP_UT"

        def fetch(self, window_start, window_end, task_id=0):
            return []

    orig = dict(AdapterFactory._registry)
    try:
        AdapterFactory.register(_TmpAdapter)
        assert "TMP_UT" in AdapterFactory.available_types()
        inst = AdapterFactory.get(_ds_config("TMP_UT", {}))
        assert isinstance(inst, _TmpAdapter)
        assert inst.type == "TMP_UT"
    finally:
        monkeypatch.setattr(AdapterFactory, "_registry", orig)


def test_adapter_factory_unknown_type():
    from capability.adapter.factory import AdapterFactory
    with pytest.raises(ValueError, match="未注册的数据源类型"):
        AdapterFactory.get(_ds_config("NOPE", {}))


def test_adapter_factory_default_registry():
    from capability.adapter.factory import AdapterFactory
    types = AdapterFactory.available_types()
    for t in ("SYSLOG", "API", "DB", "EXCEL", "INTEL", "HISTORY"):
        assert t in types


# ═══════════════════════════════════════════════════════════════
# I. rag / rag_factory / doc_loader
# ═══════════════════════════════════════════════════════════════

def test_rag_facade_disabled():
    from capability.rag.rag_facade import RAGFacade
    assert RAGFacade(enabled=False).recall("query") == []


def test_rag_facade_recall_with_results(monkeypatch):
    from capability.rag.rag_factory import RAGFactory, RetrievalResult
    from capability.rag.rag_facade import RAGFacade

    def fake_retrieve(kb, query, top_k=5):
        return RetrievalResult(query=query, kb_name=kb, kb_label=f"库{kb}",
                               items=[{"document": f"doc-{kb}-1", "score": 0.9},
                                      {"text": "doc-2", "score": 0.5}])
    monkeypatch.setattr(RAGFactory, "retrieve", staticmethod(fake_retrieve))
    refs = RAGFacade().recall("查询", kb_names=["report_guideline"], top_k=2)
    assert len(refs) == 2
    assert refs[0]["kb_name"] == "report_guideline"
    assert refs[0]["content"] == "doc-report_guideline-1"
    assert refs[1]["content"] == "doc-2"


def test_rag_facade_recall_default_kbs(monkeypatch):
    from capability.rag.rag_factory import RAGFactory, RetrievalResult
    from capability.rag.rag_facade import RAGFacade

    def fake_retrieve(kb, query, top_k=5):
        return RetrievalResult(query=query, kb_name=kb, kb_label="L",
                               items=[{"document": "d", "score": 0.1}])
    monkeypatch.setattr(RAGFactory, "retrieve", staticmethod(fake_retrieve))
    refs = RAGFacade().recall("查询", top_k=1)
    # 3 个默认 kb → refs 被切片到 top_k * len(targets) = 3
    assert len(refs) == 3


def test_rag_facade_recall_kb_exception(monkeypatch):
    from capability.rag.rag_factory import RAGFactory, RetrievalResult
    from capability.rag.rag_facade import RAGFacade

    calls = []

    def fake_retrieve(kb, query, top_k=5):
        calls.append(kb)
        if kb == "bad":
            raise RuntimeError("向量库不可用")
        return RetrievalResult(query=query, kb_name=kb, kb_label="L",
                               items=[{"document": "d", "score": 0.1}])
    monkeypatch.setattr(RAGFactory, "retrieve", staticmethod(fake_retrieve))
    refs = RAGFacade().recall("查询", kb_names=["bad", "ok"], top_k=1)
    assert refs == [] or len(refs) == 1  # bad 跳过，ok 命中
    assert calls == ["bad", "ok"]


def test_rag_facade_recall_import_error(monkeypatch):
    from capability.rag.rag_facade import RAGFacade
    import capability.rag.rag_factory as real_mod
    monkeypatch.setitem(sys.modules, "capability.rag.rag_factory", None)
    # 触发内部 import 失败 → 优雅降级
    assert RAGFacade().recall("查询") == []
    monkeypatch.setitem(sys.modules, "capability.rag.rag_factory", real_mod)


def test_rag_facade_recall_for_metric(monkeypatch):
    from capability.rag.rag_facade import RAGFacade
    captured = {}

    def fake_recall(self, query, kb_names=None, top_k=3):
        captured["query"] = query
        captured["top_k"] = top_k
        return [{"kb_name": "kb", "content": "ref"}]
    monkeypatch.setattr(RAGFacade, "recall", fake_recall)
    metric = _metric(alert={"high": 5},
                     top={"top_type": [{"type": "brute_force"}, {"type": "web_attack"}]})
    refs = RAGFacade().recall_for_metric(metric)
    assert refs[0]["content"] == "ref"
    assert "网络安全态势" in captured["query"]
    assert "高危告警 5 起" in captured["query"]
    assert "brute_force, web_attack" in captured["query"]
    assert captured["top_k"] == 2


def test_retrieval_result_dataclass():
    from capability.rag.rag_factory import RetrievalResult
    r = RetrievalResult(query="q", items=[{"document": "d"}], total=1,
                        kb_name="kb", kb_label="库")
    assert r.total == 1
    r2 = RetrievalResult(query="q2")
    assert r2.items == []
    assert r2.total == 0


def test_knowledge_base_retrieve(monkeypatch):
    from capability.rag.rag_factory import KnowledgeBase

    class _FakeStore:
        def similarity_search(self, query, k=5):
            return [{"document": "found", "score": 0.8}]

    kb = KnowledgeBase.__new__(KnowledgeBase)
    kb.kb_name = "kb1"
    kb.kb_label = "库1"
    kb.store = _FakeStore()
    result = kb.retrieve("查询", top_k=3)
    assert result.kb_name == "kb1"
    assert result.total == 1
    assert result.items[0]["document"] == "found"


def test_knowledge_base_rerank():
    from capability.rag.rag_factory import KnowledgeBase
    kb = KnowledgeBase.__new__(KnowledgeBase)
    cands = [{"score": 0.1}, {"score": 0.9}, {"score": 0.5}]
    ranked = kb.rerank("q", cands)
    assert [c["score"] for c in ranked] == [0.9, 0.5, 0.1]


def test_rag_factory_get_kb_unknown():
    from capability.rag.rag_factory import RAGFactory
    with pytest.raises(ValueError, match="未知知识库"):
        RAGFactory.get_kb("nope")


def test_rag_factory_get_kb_singleton(monkeypatch):
    from capability.rag import rag_factory as rf

    class _FakeKB:
        def __init__(self, kb_name, kb_label, persist_dir, embedding_model=None):
            self.kb_name = kb_name
            self.kb_label = kb_label
            self.persist_dir = persist_dir
            self.embedding_model = embedding_model

    orig_cls = rf.KnowledgeBase
    orig_inst = dict(rf.RAGFactory._instances)
    try:
        rf.KnowledgeBase = _FakeKB
        rf.RAGFactory._instances.clear()
        kb1 = rf.RAGFactory.get_kb("report_guideline")
        kb2 = rf.RAGFactory.get_kb("report_guideline")
        assert kb1 is kb2
        assert kb1.kb_label == "报告规范库"
        assert kb1.persist_dir  # settings.chroma_db_path
    finally:
        rf.KnowledgeBase = orig_cls
        rf.RAGFactory._instances = orig_inst


def test_rag_factory_retrieve(monkeypatch):
    from capability.rag.rag_factory import RAGFactory, RetrievalResult

    class _FakeKB:
        def retrieve(self, query, top_k=5):
            return RetrievalResult(query=query, items=[{"document": "x"}],
                                   total=1, kb_name="kb", kb_label="库")
    monkeypatch.setattr(RAGFactory, "get_kb", classmethod(lambda cls, n: _FakeKB()))
    result = RAGFactory.retrieve("report_guideline", "查询", top_k=5)
    assert result.total == 1


def test_rag_factory_kb_meta():
    from capability.rag.rag_factory import RAGFactory
    assert "report_guideline" in RAGFactory.get_available_kbs()
    assert len(RAGFactory.get_available_kbs()) == 3
    assert RAGFactory.get_kb_label("threat_intel") == "威胁情报库"
    assert RAGFactory.get_kb_label("unknown") == "unknown"


def test_doc_loader_chunk_text():
    from capability.rag.doc_loader import _chunk_text
    assert _chunk_text("short") == ["short"]
    long_text = "\n".join(f"段落{i} " + "x" * 200 for i in range(5))
    chunks = _chunk_text(long_text, max_len=300)
    assert len(chunks) >= 2
    assert all(len(c) <= 301 for c in chunks)
    # 单段超长 → 原样返回（split 后无换行可切，仅长度判断分支）
    assert _chunk_text("y" * 1000, max_len=100) == ["y" * 1000]


def test_doc_loader_flatten_json():
    from capability.rag.doc_loader import _flatten_json
    # dict 带文本字段
    items = _flatten_json({"description": "描述文本", "severity": "high",
                           "scenario_id": "S1"}, source_file="f.json")
    assert any("描述文本" in t for t, _ in items)
    assert any(m.get("scenario_id") == "S1" for _, m in items)
    # list
    items2 = _flatten_json([{"name": "a"}, {"name": "b"}])
    assert len(items2) == 2
    # 无文本字段 → 递归
    items3 = _flatten_json({"outer": {"content": "内层内容"}})
    assert any("内层内容" in t for t, _ in items3)
    # 长字符串
    items4 = _flatten_json("这是一段超过十个字符的字符串内容")
    assert items4 and items4[0][0].startswith("这是一段")
    # 短字符串/数字 → 无结果
    assert _flatten_json("short") == []
    assert _flatten_json(42) == []


def test_doc_loader_load_json_file(tmp_path):
    from capability.rag.doc_loader import _load_json_file
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"description": "内容"}), encoding="utf-8")
    items = _load_json_file(str(f))
    assert len(items) == 1
    # 文件不存在 → []
    assert _load_json_file(str(tmp_path / "missing.json")) == []
    # 非法 JSON → []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert _load_json_file(str(bad)) == []


def _fake_kb_for_ingest(initial=0):
    class _FakeStore:
        def __init__(self):
            self.n = initial
            self._client = None
            self._collection = None
            self.embed_fn = None

        def count(self):
            return self.n

        def add_documents(self, documents, metadatas, ids):
            self.n += len(documents)

    class _FakeKB:
        def __init__(self):
            self.store = _FakeStore()

    return _FakeKB


def test_doc_loader_ingest_kb_unknown(monkeypatch):
    from capability.rag.doc_loader import ingest_kb
    assert ingest_kb("unknown_kb", "/tmp") == 0


def test_doc_loader_ingest_kb_skip_when_exists(monkeypatch):
    from capability.rag.doc_loader import ingest_kb
    from capability.rag.rag_factory import RAGFactory
    FakeKB = _fake_kb_for_ingest(initial=5)
    monkeypatch.setattr(RAGFactory, "get_kb", classmethod(lambda cls, n: FakeKB()))
    assert ingest_kb("log_basics", "/tmp") == 5


def test_doc_loader_ingest_kb_imports(monkeypatch, tmp_path):
    from capability.rag.doc_loader import ingest_kb
    from capability.rag.rag_factory import RAGFactory

    rule_dir = tmp_path / "rules"
    rule_dir.mkdir()
    (rule_dir / "log_features.json").write_text(
        json.dumps([{"name": "特征A", "description": "特征描述"}]), encoding="utf-8")
    (rule_dir / "risk_rules.json").write_text(
        json.dumps({"rule_id": "R1", "detail": "规则详情"}), encoding="utf-8")

    FakeKB = _fake_kb_for_ingest(initial=0)
    monkeypatch.setattr(RAGFactory, "get_kb", classmethod(lambda cls, n: FakeKB()))
    total = ingest_kb("log_basics", str(rule_dir))
    assert total == 2


def test_doc_loader_ingest_kb_force_rebuild(monkeypatch, tmp_path):
    from capability.rag.doc_loader import ingest_kb
    from capability.rag.rag_factory import RAGFactory

    rule_dir = tmp_path / "rules"
    rule_dir.mkdir()
    (rule_dir / "log_features.json").write_text(
        json.dumps({"description": "x"}), encoding="utf-8")
    (rule_dir / "risk_rules.json").write_text(
        json.dumps({"description": "y"}), encoding="utf-8")

    FakeKB = _fake_kb_for_ingest(initial=0)
    monkeypatch.setattr(RAGFactory, "get_kb", classmethod(lambda cls, n: FakeKB()))
    # force=True 且 count==0 → 走重建分支（_client 为 None 时异常被吞）
    total = ingest_kb("log_basics", str(rule_dir), force=True)
    assert total == 2


def test_doc_loader_ingest_kb_no_data(monkeypatch, tmp_path):
    from capability.rag.doc_loader import ingest_kb
    from capability.rag.rag_factory import RAGFactory
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    FakeKB = _fake_kb_for_ingest(initial=0)
    monkeypatch.setattr(RAGFactory, "get_kb", classmethod(lambda cls, n: FakeKB()))
    assert ingest_kb("log_basics", str(empty_dir)) == 0


def test_doc_loader_ingest_all(monkeypatch, tmp_path):
    from capability.rag.doc_loader import ingest_all
    from capability.rag.rag_factory import RAGFactory

    rule_dir = tmp_path / "rules"
    rule_dir.mkdir()
    (rule_dir / "log_features.json").write_text(json.dumps({"description": "a"}), encoding="utf-8")
    (rule_dir / "risk_rules.json").write_text(json.dumps({"description": "b"}), encoding="utf-8")
    (rule_dir / "compliance_standards.json").write_text(json.dumps({"description": "c"}), encoding="utf-8")
    (rule_dir / "compliance_baselines.json").write_text(json.dumps({"description": "d"}), encoding="utf-8")

    FakeKB = _fake_kb_for_ingest(initial=0)

    def fake_get_kb(cls, kb_name):
        if kb_name == "cases":
            raise RuntimeError("cases 导入失败")
        return FakeKB()

    monkeypatch.setattr(RAGFactory, "get_kb", classmethod(fake_get_kb))
    results = ingest_all(str(rule_dir))
    assert "log_basics" in results and results["log_basics"] > 0
    assert results["cases"] == 0      # 异常 → 记 0
    assert len(results) == len(__import__("capability.rag.doc_loader", fromlist=["KB_FILE_MAP"]).KB_FILE_MAP)


# ═══════════════════════════════════════════════════════════════
# J. render
# ═══════════════════════════════════════════════════════════════

def _render_data():
    from model.struct.structs import RenderData
    return RenderData(
        cycle="MONTHLY", cycle_label="月报",
        window_start="2026-07-01 00:00:00", window_end="2026-08-01 00:00:00",
        generated_at="2026-08-06 12:00:00",
        metric={"alert": {"high": 2, "medium": 3, "low": 4, "info": 1},
                "trend": {"compare": {"alert_total": {"delta": 10}}}},
        judge={"risk_level": "HIGH",
               "sections": {"overview": "总体态势", "alert": "告警", "vuln": "漏洞",
                            "attack": "攻击", "trend": "趋势", "suggestion": "建议"}},
        extra={"title": "测试报告"},
    )


def test_renderer_factory(monkeypatch):
    from capability.render.render_base import RendererFactory, Renderer

    class _TmpRenderer(Renderer):
        ext = "txt"

        def render(self, data):
            return "txt"

        def render_to_file(self, data, file_path):
            return file_path

    orig = dict(RendererFactory._registry)
    try:
        RendererFactory.register(_TmpRenderer)
        assert "txt" in RendererFactory.available_exts()
        inst = RendererFactory.get("TXT")      # 大小写不敏感
        assert isinstance(inst, _TmpRenderer)
        with pytest.raises(ValueError, match="未注册的渲染器"):
            RendererFactory.get("nope")
    finally:
        monkeypatch.setattr(RendererFactory, "_registry", orig)


def test_md_renderer_render():
    from capability.render.md_renderer import MdRenderer
    out = MdRenderer().render(_render_data())
    assert "# 测试报告" in out
    assert "月报" in out
    assert "HIGH" in out
    assert "总体态势" in out
    assert "| 高危 | 2 |" in out


def test_md_renderer_fallback_template():
    from capability.render.md_renderer import MdRenderer
    data = _render_data()
    data.cycle = "nonexistent_cycle"
    out = MdRenderer().render(data)
    # 回退到月报模板
    assert "测试报告" in out


def test_md_renderer_render_to_file(tmp_path):
    from capability.render.md_renderer import MdRenderer
    path = str(tmp_path / "sub" / "out.md")
    abs_path = MdRenderer().render_to_file(_render_data(), path)
    assert os.path.exists(abs_path)
    assert os.path.getsize(abs_path) > 50


def test_md_renderer_build_context_defaults():
    from capability.render.md_renderer import MdRenderer
    from model.struct.structs import RenderData
    data = RenderData(cycle="DAILY", cycle_label="日报", extra={})
    ctx = MdRenderer._build_context(data)
    assert ctx["title"] == "日报网络安全态势报告"
    assert ctx["risk_level"] == "LOW"
    assert ctx["sections"] == {}
    assert ctx["compare"] is None


def test_docx_renderer_render():
    from capability.render.docx_renderer import DocxRenderer
    assert DocxRenderer().render(_render_data()) == ""


def test_docx_renderer_render_to_file(tmp_path):
    from capability.render.docx_renderer import DocxRenderer
    path = str(tmp_path / "sub" / "out.docx")
    abs_path = DocxRenderer().render_to_file(_render_data(), path)
    assert os.path.exists(abs_path)
    assert os.path.getsize(abs_path) > 1000


def test_register_renderers():
    from capability.render.register import register_renderers
    from capability.render.render_base import RendererFactory
    register_renderers()
    assert "md" in RendererFactory.available_exts()
    assert "docx" in RendererFactory.available_exts()


# ═══════════════════════════════════════════════════════════════
# K. judge
# ═══════════════════════════════════════════════════════════════

def test_risk_flag_to_dict():
    from capability.judge.rule_engine import RiskFlag
    flag = RiskFlag(rule_name="r", level="HIGH", message="m", evidence={"k": 1})
    d = flag.to_dict()
    assert d == {"rule_name": "r", "level": "HIGH", "message": "m", "evidence": {"k": 1}}


def test_rule_engine_exception_isolation():
    from capability.judge.rule_engine import RuleEngine, RiskFlag, Rule

    class _BoomRule(Rule):
        name = "boom"

        def evaluate(self, metric, context):
            raise RuntimeError("rule crash")

    class _GoodRule(Rule):
        name = "good"

        def evaluate(self, metric, context):
            return RiskFlag(rule_name="good", level="MEDIUM", message="ok")

    engine = RuleEngine([_BoomRule()])
    engine.register(_GoodRule())
    flags = engine.evaluate_all(_metric())
    assert len(flags) == 1
    assert flags[0].rule_name == "good"
    assert engine.rules[0].name == "boom"


def test_rule_engine_composite_level_ordering():
    from capability.judge.rule_engine import RuleEngine, RiskFlag
    engine = RuleEngine()
    flags = [RiskFlag(rule_name="a", level="MEDIUM", message="m"),
             RiskFlag(rule_name="b", level="LOW", message="m")]
    assert engine.composite_level(flags) == "MEDIUM"
    flags2 = [RiskFlag(rule_name="c", level="WEIRD", message="m"),
              RiskFlag(rule_name="d", level="HIGH", message="m")]
    assert engine.composite_level(flags2) == "HIGH"
    assert engine.composite_level([]) == "LOW"


def test_build_report_messages():
    from capability.judge.prompt_builder import build_report_messages
    from capability.judge.rule_engine import RiskFlag
    metric = _metric(alert={"total": 10, "high": 2})
    flags = [RiskFlag(rule_name="alert_volume", level="HIGH", message="告警超标")]
    refs = [{"kb_label": "报告规范库", "content": "参考内容" * 50}]
    msgs = build_report_messages(metric, flags, refs)
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "告警超标" in msgs[1]["content"]
    assert "参考内容" in msgs[1]["content"]
    assert "一、总体态势" in msgs[1]["content"]
    # 无 flags / 无 refs
    msgs2 = build_report_messages(metric, [], [])
    assert "无规则命中" in msgs2[1]["content"]
    assert "无知识库引用" in msgs2[1]["content"]


def test_build_report_messages_truncation(monkeypatch):
    from config.settings import settings
    from capability.judge.prompt_builder import build_report_messages
    monkeypatch.setattr(settings, "llm_max_input_chars", 80)
    msgs = build_report_messages(_metric(alert={"total": 100, "high": 3}), [], [])
    assert "...(截断)" in msgs[1]["content"]


def test_parse_llm_response():
    from capability.judge.prompt_builder import parse_llm_response
    assert parse_llm_response('{"sections": {"a": "1"}}') == {"sections": {"a": "1"}}
    # 代码块包裹
    assert parse_llm_response('```json\n{"a": 1}\n```') == {"a": 1}
    # 前后噪声
    assert parse_llm_response('说明文字 {"a": 1} 结尾') == {"a": 1}
    # 完全不可解析
    assert parse_llm_response("not json at all") == {}
    assert parse_llm_response("") == {}
    assert parse_llm_response(None) == {}


def test_fallback_sections_with_compare():
    from capability.judge.prompt_builder import build_fallback_sections
    from capability.judge.rule_engine import RiskFlag
    metric = _metric(
        alert={"total": 10, "high": 2, "close_rate": 0.5, "by_type": {"brute_force": 6}},
        vuln={"total": 5, "unfixed": 2, "unfixed_high": 1, "close_rate": 0.6,
              "top_assets": [{"asset_ip": "10.0.0.1", "count": 2}]},
        top={"top_src": [{"ip": "1.1.1.1", "count": 8}],
             "top_type": [{"type": "brute_force", "count": 6}],
             "top_asset": [{"asset": "10.0.0.2", "count": 4}]},
        trend={"by_day": [{"date": "2026-07-01", "total": 10, "high": 2}],
               "compare": {"alert_total": {"delta": "+3"}}},
    )
    flags = [RiskFlag(rule_name="alert_volume", level="HIGH", message="告警超标")]
    sections = build_fallback_sections(metric, flags)
    assert "10 起" in sections["overview"]
    assert "告警超标" in sections["overview"]
    assert "brute_force=6" in sections["alert"]
    assert "10.0.0.1" in sections["vuln"]
    assert "1.1.1.1" in sections["attack"]
    assert "+3" in sections["trend"]
    assert "1. 优先处置高危告警" in sections["suggestion"]


def test_fallback_sections_without_compare():
    from capability.judge.prompt_builder import build_fallback_sections
    metric = _metric(alert={"total": 0, "high": 0, "close_rate": 0.0},
                     vuln={}, top={}, trend={})
    sections = build_fallback_sections(metric, [])
    assert "无规则命中" in sections["overview"]
    assert "环比/同比数据暂缺" in sections["trend"]
    assert "暂无数据" in sections["attack"]


def test_prompt_manager_system_prompt():
    from capability.judge.prompt_manager import PromptManager
    sp = PromptManager.get_system_prompt()
    assert "日志安全分析助手" in sp
    sp2 = PromptManager.get_system_prompt("log_parse")
    assert "日志解析专家" in sp2
    # 未知模块 → 回退 default
    sp3 = PromptManager.get_system_prompt("unknown_mod")
    assert "准确、专业的回答" in sp3


def test_prompt_manager_build_messages():
    from capability.judge.prompt_manager import PromptManager
    msgs = PromptManager.build_messages("default", "请分析")
    assert len(msgs) == 2
    assert msgs[-1]["content"] == "请分析"
    # 带 rag 上下文
    msgs2 = PromptManager.build_messages("default", "请分析",
                                         context={"rag_context": "知识库A"})
    assert len(msgs2) == 3
    assert "知识库A" in msgs2[1]["content"]
    # system_override
    msgs3 = PromptManager.build_messages("default", "hi", system_override="自定义系统")
    assert msgs3[0]["content"] == "自定义系统"


def test_prompt_manager_get_prompt():
    from capability.judge.prompt_manager import PromptManager
    p = PromptManager.get_prompt("log_identify_fallback", log_line="<134>...")
    assert "识别到的设备类型" in p
    p2 = PromptManager.get_prompt("log_parse_fallback", log_line="x")
    assert "timestamp" in p2
    p3 = PromptManager.get_prompt("training_scoring", standard="s", submission="u")
    assert "content_match" in p3
    p4 = PromptManager.get_prompt("guide_generate", scale="中", device_types="fw",
                                  device_count=10, daily_log_volume="1T", budget="中",
                                  team_skill="中", collect_plans_json="{}",
                                  architecture_json="{}", platform_json="{}")
    assert "日志采集与分析指导手册" in p4
    with pytest.raises(ValueError, match="未知 prompt 模板"):
        PromptManager.get_prompt("nope")
    assert PromptManager.get_version() == "1.0.0"


def test_llm_factory_register_create(monkeypatch):
    from capability.judge.llm_factory import LLMFactory, BaseLLMClient

    class _TmpClient(BaseLLMClient):
        async def chat(self, messages, temperature=None, timeout=None):
            return {"success": True, "content": "x"}

        async def chat_stream(self, messages, temperature=None, timeout=None):
            yield "x"

    orig_reg = dict(LLMFactory._registry)
    orig_inst = dict(LLMFactory._instances)
    try:
        LLMFactory.register("tmp_ut", _TmpClient)
        client = LLMFactory.create("tmp_ut")
        assert isinstance(client, _TmpClient)
        main = LLMFactory.create("main")
        assert main.model_name  # settings.llm_model_name
        light = LLMFactory.create("light")
        assert light.model_name
        with pytest.raises(ValueError, match="未知模型类型"):
            LLMFactory.create("nope")
    finally:
        monkeypatch.setattr(LLMFactory, "_registry", orig_reg)
        monkeypatch.setattr(LLMFactory, "_instances", orig_inst)


@pytest.mark.asyncio
async def test_llm_factory_singletons_and_close(monkeypatch):
    from capability.judge.llm_factory import LLMFactory, BaseLLMClient

    class _Fake(BaseLLMClient):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.closed = False

        async def chat(self, messages, temperature=None, timeout=None):
            return {"success": True, "content": "c"}

        async def chat_stream(self, messages, temperature=None, timeout=None):
            yield "c"

        async def close(self):
            self.closed = True

    orig_reg = dict(LLMFactory._registry)
    orig_inst = dict(LLMFactory._instances)
    try:
        LLMFactory.register("main", _Fake)
        LLMFactory.register("light", _Fake)
        LLMFactory._instances.clear()
        m1 = await LLMFactory.get_main_llm()
        m2 = await LLMFactory.get_main_llm()
        assert m1 is m2
        l1 = await LLMFactory.get_light_llm()
        assert l1 is not m1
        await LLMFactory.close_all()
        assert m1.closed is True
        assert LLMFactory._instances == {}
    finally:
        monkeypatch.setattr(LLMFactory, "_registry", orig_reg)
        monkeypatch.setattr(LLMFactory, "_instances", orig_inst)


# ── DeepSeekClient / LightweightClient 网络路径（mock AsyncOpenAI）──

class _FakeAsyncOpenAI:
    """可配置行为的 AsyncOpenAI 替身"""
    _content = "hello"
    _error = None
    _chunks = ["tok1", "tok2"]

    def __init__(self, *args, **kwargs):
        pass

    class _Msg:
        def __init__(self, content):
            self.content = content

    class _Choice:
        def __init__(self, content):
            self.message = _FakeAsyncOpenAI._Msg(content)

    class _Resp:
        def __init__(self, content):
            self.choices = [_FakeAsyncOpenAI._Choice(content)]

    class _Delta:
        def __init__(self, content):
            self.content = content

    class _StreamChoice:
        def __init__(self, content):
            self.delta = _FakeAsyncOpenAI._Delta(content)

    class _Chunk:
        def __init__(self, content):
            self.choices = [_FakeAsyncOpenAI._StreamChoice(content)]

    class _Stream:
        def __init__(self, chunks):
            self._chunks = list(chunks)
            self._i = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._i >= len(self._chunks):
                raise StopAsyncIteration
            c = self._chunks[self._i]
            self._i += 1
            return _FakeAsyncOpenAI._Chunk(c)

    class _Completions:
        async def create(self, **kwargs):
            if _FakeAsyncOpenAI._error:
                raise _FakeAsyncOpenAI._error
            if kwargs.get("stream"):
                return _FakeAsyncOpenAI._Stream(_FakeAsyncOpenAI._chunks)
            return _FakeAsyncOpenAI._Resp(_FakeAsyncOpenAI._content)


# chat 属性在类定义完成后挂载（嵌套类体内无法引用外层类名）
_FakeAsyncOpenAI.chat = type("_FakeChat", (),
                             {"completions": _FakeAsyncOpenAI._Completions()})()


@pytest.fixture()
def _fake_openai(monkeypatch):
    _FakeAsyncOpenAI._content = "hello"
    _FakeAsyncOpenAI._error = None
    _FakeAsyncOpenAI._chunks = ["tok1", "tok2"]
    monkeypatch.setattr("capability.judge.llm_factory.AsyncOpenAI", _FakeAsyncOpenAI)
    return _FakeAsyncOpenAI


@pytest.mark.asyncio
async def test_deepseek_chat_success(_fake_openai):
    from capability.judge.llm_factory import DeepSeekClient
    client = DeepSeekClient(api_key="k", base_url="http://x", model_name="m")
    resp = await client.chat([{"role": "user", "content": "hi"}], temperature=0.1, timeout=5)
    assert resp["success"] is True
    assert resp["content"] == "hello"
    assert resp["error"] is None
    assert client.client is not None


@pytest.mark.asyncio
async def test_deepseek_chat_failure(_fake_openai):
    from capability.judge.llm_factory import DeepSeekClient
    _FakeAsyncOpenAI._error = RuntimeError("network down")
    client = DeepSeekClient(api_key="k", base_url="http://x", model_name="m")
    resp = await client.chat([{"role": "user", "content": "hi"}])
    assert resp["success"] is False
    assert "network down" in resp["error"]
    assert resp["content"] is None


@pytest.mark.asyncio
async def test_deepseek_chat_stream(_fake_openai):
    from capability.judge.llm_factory import DeepSeekClient
    client = DeepSeekClient(api_key="k", base_url="http://x", model_name="m")
    tokens = [t async for t in client.chat_stream([{"role": "user", "content": "hi"}])]
    assert tokens == ["tok1", "tok2"]


@pytest.mark.asyncio
async def test_deepseek_chat_stream_failure(_fake_openai):
    from capability.judge.llm_factory import DeepSeekClient
    _FakeAsyncOpenAI._error = RuntimeError("stream down")
    client = DeepSeekClient(api_key="k", base_url="http://x", model_name="m")
    tokens = [t async for t in client.chat_stream([{"role": "user", "content": "hi"}])]
    assert len(tokens) == 1
    assert "错误" in tokens[0]


@pytest.mark.asyncio
async def test_lightweight_chat_success(_fake_openai):
    from capability.judge.llm_factory import LightweightClient
    client = LightweightClient(api_key="k", base_url="http://x", model_name="m")
    resp = await client.chat([{"role": "user", "content": "hi"}])
    assert resp["success"] is True


@pytest.mark.asyncio
async def test_lightweight_chat_failure_and_stream(_fake_openai):
    from capability.judge.llm_factory import LightweightClient
    _FakeAsyncOpenAI._error = RuntimeError("boom")
    client = LightweightClient(api_key="k", base_url="http://x", model_name="m")
    resp = await client.chat([{"role": "user", "content": "hi"}])
    assert resp["success"] is False
    _FakeAsyncOpenAI._error = None
    tokens = [t async for t in client.chat_stream([{"role": "user", "content": "hi"}])]
    assert tokens == ["tok1", "tok2"]
    _FakeAsyncOpenAI._error = RuntimeError("stream boom")
    tokens2 = [t async for t in client.chat_stream([{"role": "user", "content": "hi"}])]
    assert "错误" in tokens2[0]


def test_base_llm_client_close():
    from capability.judge.llm_factory import BaseLLMClient

    class _C(BaseLLMClient):
        async def chat(self, messages, temperature=None, timeout=None):
            return {}

        async def chat_stream(self, messages, temperature=None, timeout=None):
            yield ""

    client = _C(api_key="k", base_url="u", model_name="m")
    assert client.temperature == 0.1
    assert client.timeout == 10
    # 无 client → close 直接返回
    import asyncio
    asyncio.run(client.close())


# ── LLMJudge ──

@pytest.mark.asyncio
async def test_llm_judge_no_api_key_fallback(monkeypatch):
    from config.settings import settings
    from capability.judge.llm_judge import LLMJudge
    monkeypatch.setattr(settings, "llm_api_key", "")
    judge = LLMJudge()
    result = await judge.judge(_metric(alert={"total": 5, "high": 1}), [])
    assert result.llm_ok is False
    assert result.llm_error == "未配置 LLM API Key"
    assert "overview" in result.sections
    assert result.risk_level == "LOW"


@pytest.mark.asyncio
async def test_llm_judge_fallback_disabled(monkeypatch):
    from config.settings import settings
    from capability.judge.llm_judge import LLMJudge
    monkeypatch.setattr(settings, "llm_api_key", "k")
    monkeypatch.setattr(settings, "llm_fallback_enabled", False)
    judge = LLMJudge()
    result = await judge.judge(_metric(), [])
    assert result.llm_ok is False


@pytest.mark.asyncio
async def test_llm_judge_success(monkeypatch):
    from config.settings import settings
    from capability.judge.llm_judge import LLMJudge
    from capability.judge.rule_engine import RiskFlag
    monkeypatch.setattr(settings, "llm_api_key", "k")

    class _FakeLLM:
        async def chat(self, messages, temperature=None):
            return {"success": True,
                    "content": '{"sections": {"overview": "总体", "alert": "告警"}, "risk_level": "HIGH"}'}

    judge = LLMJudge()
    monkeypatch.setattr(judge, "_get_llm", lambda: _FakeLLM())
    flags = [RiskFlag(rule_name="r", level="MEDIUM", message="m")]
    result = await judge.judge(_metric(), flags, rag_refs=[{"kb_label": "L", "content": "c"}])
    assert result.llm_ok is True
    assert result.sections["overview"] == "总体"
    assert result.risk_level == "HIGH"
    assert result.rag_refs == [{"kb_label": "L", "content": "c"}]
    assert result.risk_flags[0]["rule_name"] == "r"


@pytest.mark.asyncio
async def test_llm_judge_failure_degrades(monkeypatch):
    from config.settings import settings
    from capability.judge.llm_judge import LLMJudge
    from capability.judge.rule_engine import RiskFlag
    monkeypatch.setattr(settings, "llm_api_key", "k")

    class _FailLLM:
        async def chat(self, messages, temperature=None):
            return {"success": False, "error": "timeout"}

    judge = LLMJudge()
    monkeypatch.setattr(judge, "_get_llm", lambda: _FailLLM())
    flags = [RiskFlag(rule_name="r", level="HIGH", message="m")]
    result = await judge.judge(_metric(), flags)
    assert result.llm_ok is False
    assert "timeout" in result.llm_error
    assert "overview" in result.sections      # 降级模板
    assert result.risk_level == "HIGH"        # 规则标记兜底


@pytest.mark.asyncio
async def test_llm_judge_bad_json_degrades(monkeypatch):
    from config.settings import settings
    from capability.judge.llm_judge import LLMJudge
    monkeypatch.setattr(settings, "llm_api_key", "k")

    class _BadLLM:
        async def chat(self, messages, temperature=None):
            return {"success": True, "content": "not json"}

    judge = LLMJudge()
    monkeypatch.setattr(judge, "_get_llm", lambda: _BadLLM())
    result = await judge.judge(_metric(), [])
    assert result.llm_ok is False
    assert "sections" in result.llm_error


def test_llm_judge_composite():
    from capability.judge.llm_judge import LLMJudge
    from capability.judge.rule_engine import RiskFlag
    assert LLMJudge._composite([]) == "LOW"
    flags = [RiskFlag(rule_name="a", level="MEDIUM", message="m"),
             RiskFlag(rule_name="b", level="HIGH", message="m")]
    assert LLMJudge._composite(flags) == "HIGH"
    flags2 = [RiskFlag(rule_name="c", level="WEIRD", message="m")]
    # 未知等级按 0 参与排序，但 max 返回原等级字符串
    assert LLMJudge._composite(flags2) == "WEIRD"


# ═══════════════════════════════════════════════════════════════
# L. metric
# ═══════════════════════════════════════════════════════════════

class _ConcreteTemplate:
    """MetricTemplate 最小实现（模板方法测试宿主）"""
    cycle = "DAILY"

    def __init__(self):
        from capability.metric.metric_base import MetricTemplate
        self._t = MetricTemplate.__new__(MetricTemplate)
        self.calls = 0

    def build(self, events, vulns, window_start, window_end):
        self.calls += 1
        return self._t.build(events, vulns, window_start, window_end)

    def calc_alert(self, events, window_start, window_end):
        return {"total": len(events), "by_day": []}

    def calc_vuln(self, vulns, window_start, window_end):
        return {"total": len(vulns)}

    def calc_top(self, events, window_start, window_end):
        return {}

    def calc_trend(self, events, window_start, window_end):
        return {"by_day": [], "compare": {}}

    def assemble(self, alert, vuln, top, trend, window_start, window_end):
        return self._t.assemble(alert, vuln, top, trend, window_start, window_end)


def test_metric_template_build():
    from capability.metric.metric_base import MetricTemplate
    from capability.metric.aggregator import MetricAggregator

    class _Sub(MetricTemplate):
        cycle = "DAILY"

        def calc_alert(self, events, ws, we):
            return {"total": 1, "by_day": []}

        def calc_vuln(self, vulns, ws, we):
            return {"total": 0}

        def calc_top(self, events, ws, we):
            return {}

        def calc_trend(self, events, ws, we):
            return {"compare": {}}

    metric = _Sub().build([], [], "2026-07-01 00:00:00", "2026-07-02 00:00:00")
    assert metric.cycle == "DAILY"
    assert metric.alert["total"] == 1
    assert metric.raw == {"event_count": 0, "vuln_count": 0}
    assert metric.window_start == "2026-07-01 00:00:00"


def test_cached_metric_proxy_cache_hit(monkeypatch):
    from capability.metric.metric_base import CachedMetricProxy
    from capability.metric.aggregator import MetricAggregator
    from infra.cache.cache import get_cache

    cache = get_cache()
    key = "metric:DAILY:2026-07-01 00:00:00:2026-07-02 00:00:00"
    cache.delete(key)

    agg = MetricAggregator(cycle="DAILY")
    events = [_std_event(event_time="2026-07-01 10:00:00")]

    class _CountingAgg(MetricAggregator):
        def __init__(self):
            super().__init__(cycle="DAILY")
            self.build_calls = 0

        def build(self, events, vulns, ws, we):
            self.build_calls += 1
            return super().build(events, vulns, ws, we)

    cagg = _CountingAgg()
    proxy = CachedMetricProxy(cagg, ttl=3600)
    m1 = proxy.build(events, [], "2026-07-01 00:00:00", "2026-07-02 00:00:00")
    m2 = proxy.build(events, [], "2026-07-01 00:00:00", "2026-07-02 00:00:00")
    assert cagg.build_calls == 1            # 第二次命中缓存
    assert m1.alert["total"] == 1
    assert m2.alert["total"] == 1
    # 空结果不缓存
    key2 = "metric:DAILY:2026-08-01 00:00:00:2026-08-02 00:00:00"
    cache.delete(key2)
    proxy.build([], [], "2026-08-01 00:00:00", "2026-08-02 00:00:00")
    proxy.build([], [], "2026-08-01 00:00:00", "2026-08-02 00:00:00")
    assert cagg.build_calls == 3            # 空结果每次都重算
    # invalidate
    proxy.invalidate("2026-07-01 00:00:00", "2026-07-02 00:00:00")
    assert cache.get(key) is None


def test_cached_metric_proxy_aggregator_prop():
    from capability.metric.metric_base import CachedMetricProxy
    from capability.metric.aggregator import MetricAggregator
    agg = MetricAggregator(cycle="DAILY")
    proxy = CachedMetricProxy(agg)
    assert proxy.aggregator is agg


def test_aggregator_calc_alert_empty():
    from capability.metric.aggregator import MetricAggregator
    agg = MetricAggregator(cycle="DAILY")
    d = agg.calc_alert([], "2026-07-01 00:00:00", "2026-07-02 00:00:00")
    assert d == {"total": 0, "high": 0, "medium": 0, "low": 0, "info": 0,
                 "close_rate": 0.0, "by_type": {}, "by_day": {}}


def test_aggregator_calc_alert_full():
    from capability.metric.aggregator import MetricAggregator
    agg = MetricAggregator(cycle="DAILY")
    events = [
        _std_event(event_time="2026-07-01 10:00:00", risk_level="HIGH", status="closed"),
        _std_event(event_time="2026-07-01 11:00:00", risk_level="HIGH", status="open"),
        _std_event(event_time="2026-07-02 09:00:00", risk_level="LOW", status="closed"),
    ]
    d = agg.calc_alert(events, "2026-07-01 00:00:00", "2026-07-03 00:00:00")
    assert d["total"] == 3
    assert d["high"] == 2
    assert d["low"] == 1
    assert d["close_rate"] == round(2 / 3, 4)
    assert d["by_type"]["brute_force"] == 3
    assert len(d["by_day"]) == 2


def test_aggregator_calc_vuln():
    from capability.metric.aggregator import MetricAggregator
    agg = MetricAggregator(cycle="DAILY")
    assert agg.calc_vuln([], "w", "e")["total"] == 0
    vulns = [
        _std_event(event_time="2026-07-01 00:00:00", event_type="vuln",
                   risk_level="HIGH", status="unfixed", asset_ip="10.0.0.1"),
        _std_event(event_time="2026-07-01 00:00:00", event_type="vuln",
                   risk_level="HIGH", status="unfixed", asset_ip="10.0.0.1"),
        _std_event(event_time="2026-07-01 00:00:00", event_type="vuln",
                   risk_level="MEDIUM", status="fixed", asset_ip="10.0.0.2"),
        _std_event(event_time="2026-07-01 00:00:00", event_type="vuln",
                   risk_level="LOW", status="ignored", asset_ip="10.0.0.3"),
    ]
    d = agg.calc_vuln(vulns, "w", "e")
    assert d["total"] == 4
    assert d["unfixed"] == 2
    assert d["fixed"] == 1
    assert d["ignored"] == 1
    assert d["unfixed_high"] == 2
    assert d["close_rate"] == 0.25
    assert d["top_assets"][0]["asset_ip"] == "10.0.0.1"
    assert d["top_assets"][0]["count"] == 2


def test_aggregator_calc_top_and_trend():
    from capability.metric.aggregator import MetricAggregator
    agg = MetricAggregator(cycle="DAILY")
    events = [
        _std_event(event_time="2026-07-01 10:00:00", src_ip="1.1.1.1", asset_ip="10.0.0.1"),
        _std_event(event_time="2026-07-01 11:00:00", src_ip="1.1.1.1", asset_ip="10.0.0.2"),
        _std_event(event_time="2026-07-01 12:00:00", src_ip="2.2.2.2", asset_ip="10.0.0.1"),
    ]
    top = agg.calc_top(events, "w", "e")
    assert top["top_src"][0] == {"ip": "1.1.1.1", "count": 2}
    assert top["top_type"][0]["type"] == "brute_force"
    assert top["top_asset"][0]["asset"] == "10.0.0.1"
    trend = agg.calc_trend(events, "w", "e")
    assert trend["compare"] == {}
    assert trend["by_day"][0]["date"] == "2026-07-01"
    assert trend["by_day"][0]["high"] == 3


def test_aggregator_assemble_raw():
    from capability.metric.aggregator import MetricAggregator
    agg = MetricAggregator(cycle="DAILY")
    alert = {"total": 2, "by_day": [{"date": "2026-07-01", "total": 2, "high": 1}]}
    metric = agg.assemble(alert, {"total": 3}, {}, {}, "w", "e")
    assert metric.cycle == "DAILY"
    assert metric.raw == {"event_count": 2, "vuln_count": 3}


def test_aggregator_day_distribution():
    from capability.metric.aggregator import MetricAggregator
    events = [
        _std_event(event_time="2026-07-02 10:00:00", risk_level="HIGH"),
        _std_event(event_time="2026-07-01 10:00:00", risk_level="LOW"),
    ]
    days = MetricAggregator._day_distribution(events)
    assert [d["date"] for d in days] == ["2026-07-01", "2026-07-02"]
    assert days[0]["high"] == 0
    assert days[1]["high"] == 1


# ═══════════════════════════════════════════════════════════════
# M. clean
# ═══════════════════════════════════════════════════════════════

def test_clean_chain_process_stats():
    from capability.clean.data_chain import CleanChain, CleanContext, CleanHandler

    class _DropSome(CleanHandler):
        name = "drop_even"

        def handle(self, event, ctx):
            return None if event.event_type == "even" else event

    chain = CleanChain()
    assert chain.add(_DropSome()) is chain
    assert chain.handlers[0].name == "drop_even"

    ctx = CleanContext(task_id=1, cycle="DAILY")
    events = [_std_event(event_type="even"), _std_event(event_type="odd"),
              _std_event(event_type="even")]
    kept = chain.process(events, ctx)
    assert len(kept) == 1
    assert kept[0].event_type == "odd"
    assert ctx.stats["input"] == 3
    assert ctx.stats["kept"] == 1
    assert ctx.stats["dropped"] == 2
    assert ctx.stats["drop_drop_even"] == 2


def test_clean_chain_process_one():
    from capability.clean.data_chain import CleanChain, CleanContext, CleanHandler

    class _Reject(CleanHandler):
        name = "reject"

        def handle(self, event, ctx):
            return None if "bad" in event.raw_content else event

    chain = CleanChain([_Reject()])
    ctx = CleanContext()
    assert chain.process_one(_std_event(raw_content="good"), ctx) is not None
    assert chain.process_one(_std_event(raw_content="bad"), ctx) is None


def test_validate_handler():
    from capability.clean.handlers import ValidateHandler
    from capability.clean.data_chain import CleanContext
    h = ValidateHandler()
    ctx = CleanContext()
    assert h.handle(_std_event(), ctx) is not None
    bad = _std_event(event_time="")
    assert h.handle(bad, ctx) is None
    short = _std_event(event_time="2026-07-1")     # < 10 字符
    assert h.handle(short, ctx) is None


def test_dedup_handler():
    from capability.clean.handlers import DedupHandler
    from capability.clean.data_chain import CleanContext
    ctx = CleanContext()
    h = DedupHandler(noise_types=["policy"])
    e1 = _std_event(event_time="2026-07-01 10:23:45")
    e2 = _std_event(event_time="2026-07-01 10:23:59")   # 同分钟同源 → 去重
    e3 = _std_event(event_time="2026-07-01 11:00:00", risk_level="INFO", event_type="policy")
    assert h.handle(e1, ctx) is not None
    assert e1.dedup_key
    assert h.handle(e2, ctx) is None
    # INFO + policy 噪声 → 丢弃（两条路径各覆盖一次）
    assert h.handle(e3, ctx) is None
    h2 = DedupHandler()
    e4 = _std_event(event_time="2026-07-02 10:00:00", risk_level="INFO", event_type="policy")
    assert h2.handle(e4, ctx) is None      # 内置 policy 噪声规则


def test_normalize_handler():
    from capability.clean.handlers import NormalizeHandler
    from capability.clean.data_chain import CleanContext
    h = NormalizeHandler()
    ctx = CleanContext()
    e = _std_event(asset_ip="", src_ip="", risk_level="", device_source="",
                   raw_content="x" * 600,
                   extra={"asset_ip": "10.9.9.9", "src_ip": "8.8.8.8",
                          "risk_hint": "weird", "device": "waf-01"})
    out = h.handle(e, ctx)
    assert out.asset_ip == "10.9.9.9"
    assert out.src_ip == "8.8.8.8"
    assert out.risk_level == "LOW"           # 非法 hint 兜底 LOW
    assert out.device_source == "waf-01"
    assert out.raw_content.endswith("...")
    assert len(out.raw_content) == 503
    # 合法 risk_level 不改写
    e2 = _std_event(risk_level="HIGH", extra={})
    assert h.handle(e2, ctx).risk_level == "HIGH"


def test_grade_handler():
    from capability.clean.handlers import GradeHandler
    from capability.clean.data_chain import CleanContext
    h = GradeHandler()
    ctx = CleanContext()
    # brute_force LOW → 抬升 MEDIUM
    e1 = _std_event(event_type="brute_force", risk_level="LOW")
    assert h.handle(e1, ctx).risk_level == "MEDIUM"
    # lateral HIGH 保持
    e2 = _std_event(event_type="lateral", risk_level="HIGH")
    assert h.handle(e2, ctx).risk_level == "HIGH"
    # vuln fixed → INFO + status 写入
    e3 = _std_event(event_type="vuln", risk_level="HIGH",
                    extra={"vuln_status": "fixed"})
    out = h.handle(e3, ctx)
    assert out.risk_level == "INFO"
    assert out.status == "fixed"
    # 普通事件不改
    e4 = _std_event(event_type="phishing", risk_level="MEDIUM")
    assert h.handle(e4, ctx).risk_level == "MEDIUM"


def test_slice_handler():
    from capability.clean.handlers import SliceHandler
    from capability.clean.data_chain import CleanContext
    h = SliceHandler()
    ctx = CleanContext(window_start="2026-07-01 00:00:00", window_end="2026-07-31 23:59:59")
    # 窗口外 → None
    assert h.handle(_std_event(event_time="2026-06-30 23:59:59"), ctx) is None
    assert h.handle(_std_event(event_time="2026-08-01 00:00:00"), ctx) is None
    # 窗口内 → 分钟规整
    out = h.handle(_std_event(event_time="2026-07-15 10:23:45"), ctx)
    assert out.event_time == "2026-07-15 10:23:00"
    # 无窗口配置 → 不校验
    ctx2 = CleanContext()
    assert h.handle(_std_event(event_time="2020-01-01 00:00:00"), ctx2) is not None


def test_build_default_chain_full_flow():
    from capability.clean.handlers import build_default_chain
    from capability.clean.data_chain import CleanContext
    chain = build_default_chain()
    assert [h.name for h in chain.handlers] == \
        ["validate", "dedup", "normalize", "grade", "slice"]

    ctx = CleanContext(window_start="2026-07-01 00:00:00", window_end="2026-07-31 23:59:59")
    good = _std_event(event_time="2026-07-15 10:23:45", risk_level="LOW",
                      extra={"risk_hint": "MEDIUM", "device": "fw"})
    kept = chain.process([good, _std_event(event_time="")], ctx)
    assert len(kept) == 1
    # LOW 的 brute_force 被 grade 抬升
    assert kept[0].risk_level == "MEDIUM"
    assert kept[0].event_time == "2026-07-15 10:23:00"
    assert ctx.stats["dropped"] == 1


# ═══════════════════════════════════════════════════════════════
# N. push
# ═══════════════════════════════════════════════════════════════

def test_push_result_to_dict():
    from capability.push.push_strategy import PushResult
    r = PushResult(success=True, channel="local", detail="d", extra={"k": 1})
    assert r.to_dict() == {"success": True, "channel": "local",
                           "detail": "d", "extra": {"k": 1}}


def test_push_strategy_factory(monkeypatch):
    from capability.push.push_strategy import PushStrategy, PushStrategyFactory

    class _TmpPush(PushStrategy):
        channel = "tmp_ut"

        def push(self, version_info, context=None):
            return PushStrategyFactory  # 占位

    orig = dict(PushStrategyFactory._registry)
    try:
        PushStrategyFactory.register(_TmpPush)
        assert "tmp_ut" in PushStrategyFactory.available_channels()
        inst = PushStrategyFactory.get("tmp_ut")
        assert isinstance(inst, _TmpPush)
        with pytest.raises(ValueError, match="未注册的推送渠道"):
            PushStrategyFactory.get("nope")
    finally:
        monkeypatch.setattr(PushStrategyFactory, "_registry", orig)


def test_local_push_existing_file(monkeypatch):
    from infra.storage import file_store
    from capability.push.local_strategy import LocalPushStrategy

    monkeypatch.setattr(file_store, "file_exists", lambda p: True)
    result = LocalPushStrategy().push({"file_path": "/tmp/report.md"})
    assert result.success is True
    assert "已归档" in result.detail


def test_local_push_content_fallback(monkeypatch, tmp_path):
    from infra.storage import file_store
    from capability.push.local_strategy import LocalPushStrategy

    monkeypatch.setattr(file_store, "file_exists", lambda p: False)
    target = str(tmp_path / "report.md")
    monkeypatch.setattr(file_store, "build_report_path",
                        lambda *a, **k: target)
    saved = {}
    monkeypatch.setattr(file_store, "save_file",
                        lambda content, path: saved.update(content=content, path=path) or path)
    result = LocalPushStrategy().push({"content_md": "# 报告", "cycle": "daily", "version_no": 2})
    assert result.success is True
    assert saved["content"] == "# 报告"
    assert "实时落盘" in result.detail


def test_local_push_no_content():
    from capability.push.local_strategy import LocalPushStrategy
    result = LocalPushStrategy().push({})
    assert result.success is False
    assert "无内容" in result.detail


def test_webhook_stub_push_ok():
    from capability.push.webhook_strategies import DingTalkPushStrategy, WeComPushStrategy, EmailPushStrategy
    for cls in (DingTalkPushStrategy, WeComPushStrategy, EmailPushStrategy):
        result = cls().push({"title": "安全日报", "content_md": "# 标题\n" + "x" * 100})
        assert result.success is True
        assert result.extra["mock"] is True
        assert "模拟发送" in result.detail
        assert result.channel == cls.channel
        assert len(result.extra["summary"]) <= 81


def test_webhook_stub_push_empty():
    from capability.push.webhook_strategies import DingTalkPushStrategy
    result = DingTalkPushStrategy().push({})
    assert result.success is False
    assert "无内容" in result.detail


# ═══════════════════════════════════════════════════════════════
# O. 空 __init__ 模块可导入
# ═══════════════════════════════════════════════════════════════

def test_capability_package_imports():
    import capability
    import capability.message
    import capability.data_adapter
    import capability.render
    import capability.judge
    import capability.metric
    assert capability.__name__ == "capability"
