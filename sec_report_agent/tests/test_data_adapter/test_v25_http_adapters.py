"""V2.5 真实对接适配器测试 — EsAdapter / ApiAdapter(HTTP) / DbAdapter(DB)

测试内自起本地协议服务（复用 mock_data_services.Handler），验证真实 HTTP 对接：
认证、分页、时间窗口过滤、search_after 翻页、错误认证失败路径。
DbAdapter 用 SQLite 真库验证 db_mode 代码路径（与 MySQL 仅驱动不同）。
"""

import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from capability.adapter.es_adapter import EsAdapter
from capability.adapter.api_adapter import ApiAdapter
from capability.adapter.db_adapter import DbAdapter
from scripts.dev.mock_data_services import Handler


class _Cfg:
    def __init__(self, stype, cfg, name="t"):
        self.type = stype
        self.config_json = cfg
        self.name = name


@pytest.fixture(scope="module")
def dev_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_es_test_connection_ok(dev_server):
    es = EsAdapter(_Cfg("ES", {"es_url": dev_server, "index_pattern": "security-alerts-*"}))
    ok, msg = es.test_connection()
    assert ok
    assert "dev-cluster" in msg


def test_es_fetch_window_and_pagination(dev_server):
    es = EsAdapter(_Cfg("ES", {
        "es_url": dev_server,
        "index_pattern": "security-alerts-*",
        "time_field": "@timestamp",
        "size": "15",
    }))
    rows = es.fetch("2026-08-07 00:00:00", "2026-08-07 23:59:59")
    assert len(rows) == 40          # 全部在窗口内, 15/页 → 3 页翻页
    assert rows[0]["source_type"] == "ES"
    assert rows[0]["extra"]["risk_hint"] in ("HIGH", "MEDIUM", "LOW")


def test_es_fetch_narrow_window(dev_server):
    es = EsAdapter(_Cfg("ES", {
        "es_url": dev_server,
        "index_pattern": "security-alerts-*",
        "time_field": "@timestamp",
    }))
    rows = es.fetch("2026-08-07 06:00:00", "2026-08-07 07:00:00")
    assert len(rows) == 2           # 30 分钟粒度 → 恰好 2 条
    assert all(r["receive_time"] >= "2026-08-07T06:00:00.000Z" for r in rows)


def test_api_http_fetch_pagination(dev_server):
    api = ApiAdapter(_Cfg("API", {
        "endpoint": f"{dev_server}/api/v1/alerts",
        "auth_type": "apikey",
        "token": "dev-key-123",
        "time_field": "time",
        "page_size": "10",
    }))
    assert api._is_http_mode()
    rows = api.fetch("2026-08-07 00:00:00", "2026-08-07 23:59:59")
    assert len(rows) == 30          # 10/页 → 3 页
    assert rows[0]["extra"]["event_type"] == "web_attack_0"   # 无 event_type 时回退 name


def test_api_http_bad_auth_fails(dev_server):
    api = ApiAdapter(_Cfg("API", {
        "endpoint": f"{dev_server}/api/v1/alerts",
        "auth_type": "apikey",
        "token": "wrong-key",
    }))
    ok, msg = api.test_connection()
    assert not ok
    assert "401" in msg


def test_api_file_mode_backward_compat():
    """旧 file_path 配置仍走文件模式（V1.0 兼容）"""
    from capability.adapter.mock_data_gen import ensure_mock_files
    paths = ensure_mock_files(force=False)
    api = ApiAdapter(_Cfg("API", {"file_path": paths["api"]}))
    assert not api._is_http_mode()
    rows = api.fetch("2025-01-01 00:00:00", "2026-12-31 23:59:59")
    assert len(rows) > 0


def test_db_mode_with_sqlite():
    """db_url 模式用 SQLite 真库验证：连库/窗口过滤/字段映射"""
    tmp = tempfile.mktemp(suffix=".db")
    import sqlite3
    conn = sqlite3.connect(tmp)
    conn.execute("""CREATE TABLE vuln_ledger (
        id INTEGER PRIMARY KEY, asset_ip TEXT, asset_name TEXT, vuln_name TEXT,
        cvss REAL, risk_level TEXT, status TEXT, source_name TEXT, discover_time TEXT)""")
    conn.executemany(
        "INSERT INTO vuln_ledger (asset_ip,asset_name,vuln_name,cvss,risk_level,status,source_name,discover_time) VALUES (?,?,?,?,?,?,?,?)",
        [("10.0.2.4", "web-01", "Apache Struts RCE", 9.8, "HIGH", "open", "nessus", "2026-08-01 10:20:00"),
         ("10.0.1.3", "app-01", "OpenSSL 漏洞", 5.6, "MEDIUM", "closed", "nessus", "2026-07-20 09:00:00")])
    conn.commit()
    conn.close()
    try:
        db = DbAdapter(_Cfg("DB", {
            "db_url": f"sqlite:///{tmp}",
            "table": "vuln_ledger",
            "time_field": "discover_time",
            "extra_fields": '{"asset_owner": "asset_name"}',
        }))
        ok, msg = db.test_connection()
        assert ok
        rows = db.fetch("2026-08-01 00:00:00", "2026-08-31 23:59:59")
        assert len(rows) == 1       # 7 月的被窗口过滤
        assert rows[0]["extra"]["vuln_name"] == "Apache Struts RCE"
        assert rows[0]["extra"]["asset_owner"] == "web-01"   # 字段映射生效
    finally:
        os.remove(tmp)


def test_db_file_mode_backward_compat():
    from capability.adapter.mock_data_gen import ensure_mock_files
    paths = ensure_mock_files(force=False)
    db = DbAdapter(_Cfg("DB", {"file_path": paths["vuln"]}))
    assert not db._is_db_mode()
    rows = db.fetch("2025-01-01 00:00:00", "2026-12-31 23:59:59")
    assert len(rows) > 0
