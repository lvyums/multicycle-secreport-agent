"""V2.0 基础设施与工具层覆盖率测试 — common/utils + common/validator + common/exception
+ infra(cache/vector/storage/schedule/db/trace)

覆盖目标:
- common/utils 6 文件: file_util / ip_util / json_util / result_util / str_util / time_util 90%+
- common/validator/validator.py + common/exception/exception.py
- infra/cache/cache.py (MemoryCache/RedisCache/get_cache)
- infra/vector/vector_store.py (N-gram 嵌入 / EmbeddingCache / VectorStore 主路径与降级)
- infra/storage/file_store.py
- infra/schedule/simple_scheduler.py
- infra/db/repositories.py + infra/db/session.py + infra/trace/trace.py
"""
import sys
sys.path.insert(0, ".")

# ─────────────────────────────────────────────────────────────
# 兼容性 shim（仅测试侧，不改业务代码）：
# 业务代码用短路径 `from common.logger import LogManager`，但 common/logger/__init__.py
# 为空；json_util 还引用了顶层 `from common.file_util import read_file`（不存在）。
# 这里在测试进程内把符号挂载好，使被测模块可被导入。
# ─────────────────────────────────────────────────────────────
import types as _types

import common.logger as _logger_pkg
import common.logger.logger as _logger_impl
_logger_pkg.LogManager = _logger_impl.LogManager

import common.utils.file_util as _fu
_fake_file_util = _types.ModuleType("common.file_util")
_fake_file_util.read_file = _fu.read_file
sys.modules["common.file_util"] = _fake_file_util

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta

import numpy as np
import pytest

# ── common/utils ──
from common.utils import file_util, ip_util, str_util, time_util, result_util
from common.utils.json_util import JsonConfigLoader
from common.validator.validator import (
    validate_required, validate_enum, validate_range, parse_datetime, validate_window,
)
from common.exception.exception import (
    SecReportError, BusinessError, NotFoundError, DataSourceError,
    ScheduleError, LLMError, TemplateError, StorageError, AuthError,
)

# ── infra ──
import infra.cache.cache as cache_mod
from infra.cache.cache import BaseCache, MemoryCache, RedisCache, get_cache
from infra.storage import file_store
from infra.schedule.simple_scheduler import parse_cron, SimpleScheduler
from infra.trace.trace import generate_trace_id, set_trace_id, get_trace_id, TraceMiddleware
from infra.db.session import _normalize_url, init_db, SessionLocal, get_db, engine, DATABASE_URL
import infra.vector.vector_store as vs_mod
from infra.vector.vector_store import (
    NGramEmbeddingFunction, EmbeddingCache, VectorStore,
    get_embedding_function, KNOWN_DIMENSIONS, BGEEmbeddingFunction,
)
from infra.db import repositories as repos
from model.entity import entities as ent


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ═══════════════════════════════════════════════════════════════
# common/utils/file_util.py
# ═══════════════════════════════════════════════════════════════

def test_read_file_ok(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello", encoding="utf-8")
    assert file_util.read_file(str(p)) == "hello"


def test_read_file_missing(tmp_path):
    assert file_util.read_file(str(tmp_path / "nope.txt")) is None


def test_read_file_bad_encoding(tmp_path):
    p = tmp_path / "bin.dat"
    p.write_bytes(b"\xff\xfe\x00\x80")
    assert file_util.read_file(str(p)) is None


def test_save_file_creates_dirs(tmp_path):
    target = tmp_path / "x" / "y" / "f.txt"
    assert file_util.save_file("content", str(target)) is True
    assert target.read_text(encoding="utf-8") == "content"


def test_save_file_io_error(tmp_path):
    # 目标路径是目录 → open 抛 IsADirectoryError(IOError) → False
    d = tmp_path / "adir"
    d.mkdir()
    assert file_util.save_file("x", str(d)) is False


def test_parse_upload_file(tmp_path):
    p = tmp_path / "log.txt"
    p.write_text("  line1  \n\nline2\r\n   \nline3", encoding="utf-8")
    assert file_util.parse_upload_file(str(p)) == ["line1", "line2", "line3"]


def test_parse_upload_file_missing(tmp_path):
    assert file_util.parse_upload_file(str(tmp_path / "missing.log")) == []


def test_get_file_extension():
    assert file_util.get_file_extension("a/b/c.TXT") == ".txt"
    assert file_util.get_file_extension("noext") == ""
    assert file_util.get_file_extension("dir.with.dot/file.md") == ".md"


# ═══════════════════════════════════════════════════════════════
# common/utils/ip_util.py
# ═══════════════════════════════════════════════════════════════

def test_parse_ip_finds_all():
    assert ip_util.parse_ip("attack from 192.168.1.1 and 10.0.0.2:8080") == ["192.168.1.1", "10.0.0.2"]


def test_parse_ip_none():
    assert ip_util.parse_ip("no ip here") == []


def test_is_private_ip_ranges():
    assert ip_util.is_private_ip("10.0.0.1") is True
    assert ip_util.is_private_ip("10.255.255.255") is True
    assert ip_util.is_private_ip("172.16.0.0") is True
    assert ip_util.is_private_ip("172.31.255.255") is True
    assert ip_util.is_private_ip("192.168.0.1") is True
    assert ip_util.is_private_ip("192.168.255.255") is True


def test_is_private_ip_public():
    assert ip_util.is_private_ip("8.8.8.8") is False
    assert ip_util.is_private_ip("172.32.0.1") is False
    assert ip_util.is_private_ip("11.0.0.1") is False


def test_is_private_ip_invalid():
    assert ip_util.is_private_ip("not-an-ip") is False
    assert ip_util.is_private_ip("1.2.3") is False      # IndexError 分支
    assert ip_util.is_private_ip("") is False
    assert ip_util.is_private_ip("999.999.999.999") is False


def test_get_ip_location():
    assert ip_util.get_ip_location("192.168.1.1") == "内网地址"
    assert ip_util.get_ip_location("8.8.8.8") == "外部地址"


# ═══════════════════════════════════════════════════════════════
# common/utils/json_util.py
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _clean_json_cache():
    JsonConfigLoader.clear_cache()
    yield
    JsonConfigLoader.clear_cache()


def test_json_load_and_cache(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"a": {"b": 1}}', encoding="utf-8")
    data = JsonConfigLoader.load(str(p))
    assert data == {"a": {"b": 1}}
    # 命中缓存：改文件后仍返回旧值
    p.write_text('{"a": {"b": 2}}', encoding="utf-8")
    assert JsonConfigLoader.load(str(p)) == {"a": {"b": 1}}


def test_json_reload(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"k": "v1"}', encoding="utf-8")
    assert JsonConfigLoader.load(str(p)) == {"k": "v1"}
    p.write_text('{"k": "v2"}', encoding="utf-8")
    assert JsonConfigLoader.reload(str(p)) == {"k": "v2"}
    assert JsonConfigLoader.load(str(p)) == {"k": "v2"}


def test_json_load_missing_and_invalid(tmp_path):
    assert JsonConfigLoader.load(str(tmp_path / "missing.json")) is None
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert JsonConfigLoader.load(str(p)) is None


def test_json_get_nested(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"server": {"host": "10.0.0.1", "ports": [1, 2]}}', encoding="utf-8")
    assert JsonConfigLoader.get(str(p), "server.host") == "10.0.0.1"
    assert JsonConfigLoader.get(str(p), "server.ports") == [1, 2]
    assert JsonConfigLoader.get(str(p), "server.nope", "def") == "def"
    assert JsonConfigLoader.get(str(p), "server.ports.x", "def") == "def"  # 中间非 dict
    assert JsonConfigLoader.get(str(p), "missing", 42) == 42
    assert JsonConfigLoader.get(str(p), "") == {"server": {"host": "10.0.0.1", "ports": [1, 2]}}
    assert JsonConfigLoader.get(str(tmp_path / "nope.json"), "k", "d") == "d"  # data None


def test_json_clear_cache(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"v": 1}', encoding="utf-8")
    JsonConfigLoader.load(str(p))
    JsonConfigLoader.clear_cache(str(p))
    assert JsonConfigLoader._cache == {}
    p.write_text('{"v": 2}', encoding="utf-8")
    JsonConfigLoader.load(str(p))
    JsonConfigLoader.clear_cache()
    assert JsonConfigLoader._cache == {}


# ═══════════════════════════════════════════════════════════════
# common/utils/result_util.py
# ═══════════════════════════════════════════════════════════════

def test_result_ok():
    r = result_util.Result.ok(data={"x": 1}, msg="done")
    assert r["code"] == 0 and r["msg"] == "done" and r["data"] == {"x": 1}
    assert isinstance(r["timestamp"], int) and r["timestamp"] > 0
    r2 = result_util.Result.ok()
    assert r2["data"] == {} and r2["msg"] == "success"


def test_result_fail():
    r = result_util.Result.fail("bad")
    assert r["code"] == 400 and r["msg"] == "bad" and r["data"] == {}
    r2 = result_util.Result.fail("denied", code=403, data=[1])
    assert r2["code"] == 403 and r2["data"] == [1]


def test_result_from_exception():
    r = result_util.Result.from_exception(500, "boom")
    assert r["code"] == 500 and r["msg"] == "boom" and r["data"] == {}
    assert isinstance(r["timestamp"], int)


# ═══════════════════════════════════════════════════════════════
# common/utils/str_util.py
# ═══════════════════════════════════════════════════════════════

def test_clean_special_chars():
    assert str_util.clean_special_chars("a\x00b\r\nc\rd") == "ab\nc\nd"
    assert str_util.clean_special_chars("  padded  ") == "padded"


def test_clean_syslog_prefix():
    assert str_util.clean_syslog_prefix("<13>Mar 15 10:30:25 server sshd[1]: msg") == "sshd[1]: msg"
    assert str_util.clean_syslog_prefix("Mar 15 10:30:25 host plain") == "plain"
    assert str_util.clean_syslog_prefix("INFO: something") == "something"
    assert str_util.clean_syslog_prefix("warn: low") == "low"
    assert str_util.clean_syslog_prefix("2026-08-01T10:30:25.123Z host app: msg") == "app: msg"


def test_is_gibberish():
    assert str_util.is_gibberish("") is True
    assert str_util.is_gibberish("   ") is True
    assert str_util.is_gibberish("\x00\x01\x02") is True
    assert str_util.is_gibberish("正常的安全日志内容 123") is False
    assert str_util.is_gibberish("hello world") is False


def test_truncate():
    assert str_util.truncate("short") == "short"
    long_text = "word " * 500
    out = str_util.truncate(long_text, max_length=100)
    assert out.endswith("...") and len(out) <= 104
    assert str_util.truncate("a b c d", max_length=3) == "a..."


def test_extract_ip_from_str():
    assert str_util.extract_ip_from_str("src=10.1.2.3 port=80") == "10.1.2.3"
    assert str_util.extract_ip_from_str("no ip") is None


def test_normalize_whitespace():
    assert str_util.normalize_whitespace("  a   b\n\tc  ") == "a b c"


# ═══════════════════════════════════════════════════════════════
# common/utils/time_util.py
# ═══════════════════════════════════════════════════════════════

def test_parse_log_time_syslog():
    out = time_util.parse_log_time("Mar 15 10:30:25 server sshd")
    assert out.startswith(f"{datetime.now().year}-03-15T10:30:25")


def test_parse_log_time_apache():
    out = time_util.parse_log_time('[10/Oct/2023:13:55:36 +0000] "GET /"')
    assert out.startswith("2023-10-10T13:55:36+00:00")


def test_parse_log_time_iso_no_z():
    assert time_util.parse_log_time("2023-10-10T13:55:36") == "2023-10-10T13:55:36"


def test_parse_log_time_mysql():
    assert time_util.parse_log_time("2023-10-10 13:55:36") == "2023-10-10T13:55:36"


def test_parse_log_time_empty():
    assert time_util.parse_log_time("") is None
    assert time_util.parse_log_time(None) is None


def test_parse_log_time_fallback_and_bad_value():
    # 无时间戳 → 兜底当前时间（秒级比较，避免微秒竞态）
    now_sec = datetime.now().isoformat()[:19]
    out = time_util.parse_log_time("just some text")
    assert out[:19] == now_sec
    # 模式匹配但 strptime 失败(非法日) → 走 except ValueError: continue → 兜底
    out2 = time_util.parse_log_time("Mar 32 10:30:25 nonsense")
    assert out2[:19] == now_sec


def test_format_timestamp():
    dt = datetime(2023, 1, 2, 3, 4, 5)
    assert time_util.format_timestamp(dt) == "2023-01-02 03:04:05"
    assert time_util.format_timestamp(dt, "%Y/%m/%d") == "2023/01/02"
    now_str = time_util.format_timestamp()
    assert now_str.startswith(str(datetime.now().year))


# ═══════════════════════════════════════════════════════════════
# common/validator/validator.py
# ═══════════════════════════════════════════════════════════════

def test_validate_required_ok():
    validate_required("x", "f")
    validate_required(0, "f")
    validate_required(False, "f")
    validate_required([1], "f")
    validate_required({"a": 1}, "f")


def test_validate_required_errors():
    with pytest.raises(BusinessError) as e:
        validate_required(None, "f")
    assert e.value.code == 400
    with pytest.raises(BusinessError):
        validate_required("   ", "f")
    with pytest.raises(BusinessError):
        validate_required([], "f")
    with pytest.raises(BusinessError):
        validate_required({}, "f")
    with pytest.raises(BusinessError):
        validate_required((), "f")


def test_validate_enum():
    validate_enum("DAILY", ["DAILY", "WEEKLY"], "cycle")
    with pytest.raises(BusinessError) as e:
        validate_enum("HOURLY", ["DAILY", "WEEKLY"], "cycle")
    assert "DAILY" in e.value.message


def test_validate_range():
    validate_range(5, "n", min_value=1, max_value=10)
    validate_range(1, "n", min_value=1)
    validate_range(10, "n", max_value=10)
    with pytest.raises(BusinessError):
        validate_range("5", "n")
    with pytest.raises(BusinessError):
        validate_range(True, "n")
    with pytest.raises(BusinessError) as e:
        validate_range(0, "n", min_value=1)
    assert "不能小于" in e.value.message
    with pytest.raises(BusinessError):
        validate_range(11, "n", max_value=10)


def test_parse_datetime_ok():
    assert parse_datetime("2026-08-01") == datetime(2026, 8, 1)
    assert parse_datetime("2026-08-01 00:00:00") == datetime(2026, 8, 1)
    assert parse_datetime("2026-08-01 10:30") == datetime(2026, 8, 1, 10, 30)
    assert parse_datetime("2026-08-01T10:30:00") == datetime(2026, 8, 1, 10, 30)


def test_parse_datetime_errors():
    with pytest.raises(BusinessError):
        parse_datetime("")
    with pytest.raises(BusinessError):
        parse_datetime("not-a-date")
    with pytest.raises(BusinessError) as e:
        parse_datetime("2026/08/01")
    assert "时间格式非法" in e.value.message


def test_validate_window_ok():
    s, e = validate_window("2026-08-01 00:00:00", "2026-08-06 00:00:00")
    assert s == datetime(2026, 8, 1) and e == datetime(2026, 8, 6)


def test_validate_window_errors():
    with pytest.raises(BusinessError):
        validate_window("2026-08-06", "2026-08-01")
    with pytest.raises(BusinessError) as e:
        validate_window("2025-01-01", "2026-08-01", max_days=370)
    assert "跨度" in e.value.message
    with pytest.raises(BusinessError):
        validate_window("", "2026-08-01")


# ═══════════════════════════════════════════════════════════════
# common/exception/exception.py
# ═══════════════════════════════════════════════════════════════

def test_exception_hierarchy_and_defaults():
    assert issubclass(BusinessError, SecReportError)
    e = BusinessError("参数错误")
    assert e.message == "参数错误" and e.code == 1001 and e.data == {}
    assert str(e) == "参数错误"

    nf = NotFoundError()
    assert nf.code == 404 and nf.message == "资源不存在"
    ds = DataSourceError()
    assert ds.code == 2001
    sc = ScheduleError()
    assert sc.code == 3001
    llm = LLMError()
    assert llm.code == 4001
    tp = TemplateError()
    assert tp.code == 5001
    st = StorageError()
    assert st.code == 6001
    au = AuthError()
    assert au.code == 401


def test_exception_custom_args():
    e = SecReportError("msg", code=42, data={"k": "v"})
    assert e.code == 42 and e.data == {"k": "v"}
    nf = NotFoundError("找不到", code=400, data={"id": 1})
    assert nf.message == "找不到" and nf.code == 400 and nf.data == {"id": 1}
    # 无 data → 默认 {}
    assert BusinessError("x").data == {}
    # 可捕获为基类
    with pytest.raises(SecReportError):
        raise AuthError("无权限")
    with pytest.raises(Exception):
        raise StorageError()


# ═══════════════════════════════════════════════════════════════
# infra/cache/cache.py
# ═══════════════════════════════════════════════════════════════

def test_base_cache_abstract():
    b = BaseCache()
    with pytest.raises(NotImplementedError):
        b.get("k")
    with pytest.raises(NotImplementedError):
        b.set("k", "v")
    with pytest.raises(NotImplementedError):
        b.delete("k")
    with pytest.raises(NotImplementedError):
        b.exists("k")


def test_memory_cache_basic():
    c = MemoryCache()
    assert c.get("missing") is None
    c.set("a", {"x": 1})
    assert c.get("a") == {"x": 1}
    assert c.exists("a") is True
    c.delete("a")
    assert c.get("a") is None
    assert c.exists("a") is False
    c.delete("a")  # 幂等


def test_memory_cache_ttl(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(cache_mod.time, "time", lambda: clock[0])
    c = MemoryCache()
    c.set("k", "v", ttl=10)          # expire_at=1010
    assert c.get("k") == "v"
    clock[0] = 1011                  # 过期
    assert c.get("k") is None
    c.set("noexp", "v", ttl=0)       # ttl<=0 → 永不过期
    c.set("noexp2", "v", ttl=-5)
    clock[0] = 99999
    assert c.get("noexp") == "v"
    assert c.get("noexp2") == "v"


class _FakeRedis:
    """dict 实现 redis-py 接口，供 RedisCache 测试"""

    def __init__(self):
        self.store = {}
        self.fail = False

    def get(self, key):
        if self.fail:
            raise ConnectionError("boom")
        return self.store.get(key)

    def set(self, key, value, ex=None):
        if self.fail:
            raise ConnectionError("boom")
        self.store[key] = value

    def delete(self, key):
        if self.fail:
            raise ConnectionError("boom")
        self.store.pop(key, None)

    def exists(self, key):
        if self.fail:
            raise ConnectionError("boom")
        return 1 if key in self.store else 0


@pytest.fixture()
def fake_redis(monkeypatch):
    import redis as redis_mod
    fake = _FakeRedis()
    monkeypatch.setattr(redis_mod.Redis, "from_url", lambda url, decode_responses=False: fake)
    return fake


def test_redis_cache_roundtrip(fake_redis):
    c = RedisCache("redis://x/0")
    c.set("k", {"a": 1}, ttl=60)
    assert fake_redis.store["k"] == json.dumps({"a": 1}, ensure_ascii=False)
    assert c.get("k") == {"a": 1}
    assert c.exists("k") is True
    c.delete("k")
    assert c.get("k") is None
    assert c.exists("k") is False


def test_redis_cache_ttl_none(fake_redis):
    c = RedisCache("redis://x/0")
    c.set("k", "v", ttl=0)
    assert fake_redis.store["k"] == '"v"'


def test_redis_cache_exceptions(fake_redis):
    c = RedisCache("redis://x/0")
    fake_redis.fail = True
    assert c.get("k") is None
    c.set("k", "v")      # 不抛
    c.delete("k")        # 不抛
    assert c.exists("k") is False


def test_redis_cache_bad_json(fake_redis):
    c = RedisCache("redis://x/0")
    fake_redis.store["bad"] = "{not json"
    assert c.get("bad") is None


def test_get_cache_memory_singleton(monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "cache_backend", "memory")
    monkeypatch.setattr(cache_mod, "_cache_instance", None)
    c1 = get_cache()
    c2 = get_cache()
    assert isinstance(c1, MemoryCache)
    assert c1 is c2


def test_get_cache_redis_fallback(monkeypatch):
    monkeypatch.setattr(cache_mod, "_cache_instance", None)
    from config.settings import settings
    monkeypatch.setattr(settings, "cache_backend", "redis")
    monkeypatch.setattr(cache_mod, "RedisCache", lambda url: (_ for _ in ()).throw(RuntimeError("no redis")))
    c = get_cache()
    assert isinstance(c, MemoryCache)


def test_get_cache_redis_ok(monkeypatch):
    monkeypatch.setattr(cache_mod, "_cache_instance", None)
    from config.settings import settings
    monkeypatch.setattr(settings, "cache_backend", "redis")
    created = {}

    class _FakeRedisCache:
        def __init__(self, url):
            created["url"] = url
            self.probed = False

        def set(self, k, v, ttl=5):
            self.probed = True

    monkeypatch.setattr(cache_mod, "RedisCache", _FakeRedisCache)
    c = get_cache()
    assert isinstance(c, _FakeRedisCache)
    assert c.probed is True
    assert created["url"] == settings.redis_url


# ═══════════════════════════════════════════════════════════════
# infra/storage/file_store.py
# ═══════════════════════════════════════════════════════════════

def test_safe_cycle():
    assert file_store._safe_cycle("DAILY") == "daily"
    assert file_store._safe_cycle("") == "unknown"
    assert file_store._safe_cycle(None) == "unknown"


def test_build_report_path(monkeypatch, tmp_path):
    from config.settings import settings
    monkeypatch.setattr(settings, "report_root", str(tmp_path))
    p = file_store.build_report_path("WEEKLY", version_no=3, ext="docx")
    now = datetime.now()
    assert p.startswith(str(tmp_path))
    assert f"{now.year}" in p and f"{now.month:02d}" in p
    assert os.path.exists(os.path.dirname(p))
    fname = os.path.basename(p)
    assert fname.startswith("weekly_") and fname.endswith("_v3.docx")


def test_file_store_save_read_exists_delete(tmp_path):
    target = tmp_path / "sub" / "r.md"
    abs_path = file_store.save_file("报告内容", str(target))
    assert abs_path == os.path.abspath(str(target))
    assert os.path.exists(abs_path)
    assert file_store.read_file(abs_path) == "报告内容"
    assert file_store.file_exists(abs_path) is True
    assert file_store.delete_file(abs_path) is True
    assert file_store.file_exists(abs_path) is False


def test_file_store_missing_read():
    assert file_store.read_file("") == ""
    assert file_store.read_file("/nonexistent/path/x.md") == ""


def test_file_store_read_error(tmp_path):
    d = tmp_path / "adir"
    d.mkdir()
    assert file_store.read_file(str(d)) == ""  # IsADirectoryError → ""


def test_file_store_delete_missing_and_empty():
    assert file_store.delete_file("") is False
    assert file_store.delete_file("/nonexistent/path/x.md") is False
    assert file_store.file_exists("") is False


def test_file_store_delete_error(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("x", encoding="utf-8")
    monkeypatch.setattr(file_store.os, "remove", lambda f: (_ for _ in ()).throw(PermissionError("locked")))
    assert file_store.delete_file(str(p)) is False


# ═══════════════════════════════════════════════════════════════
# infra/schedule/simple_scheduler.py
# ═══════════════════════════════════════════════════════════════

def test_parse_cron_star_and_step():
    cron = parse_cron("* * * * *")
    assert cron == [set(), set(), set(), set(), set()]
    cron2 = parse_cron("*/15 * * * *")
    assert cron2[0] == set(range(0, 60, 15))
    cron3 = parse_cron("5/20 * * * *")
    assert cron3[0] == {5, 25, 45}


def test_parse_cron_range_and_list():
    cron = parse_cron("10-12 1,2,3 * * 0-6")
    assert cron[0] == {10, 11, 12}
    assert cron[1] == {1, 2, 3}
    assert cron[4] == {0, 1, 2, 3, 4, 5, 6}


def test_parse_cron_invalid_field_count():
    with pytest.raises(ValueError):
        parse_cron("0 2 1")
    with pytest.raises(ValueError):
        parse_cron("0 2 1 * * *")


def test_scheduler_register_remove():
    s = SimpleScheduler()
    s.add_cron_job("c1", "0 1 * * *", lambda: None, 1, x=2)
    s.add_interval_job("i1", 60, lambda: None)
    assert "c1" in s._jobs and s._jobs["c1"]["interval_seconds"] is None
    assert s._jobs["i1"]["interval_seconds"] == 60
    s.remove_job("c1")
    s.remove_job("nope")  # 幂等
    assert "c1" not in s._jobs


def test_match_cron():
    now = datetime(2026, 8, 6, 1, 0)  # 周四
    assert SimpleScheduler._match_cron([set(), set(), set(), set(), set()], now) is True
    assert SimpleScheduler._match_cron([{5}, set(), set(), set(), set()], now) is False
    assert SimpleScheduler._match_cron([{0}, {2}, set(), set(), set()], now) is False
    assert SimpleScheduler._match_cron([{0}, {1}, {7}, set(), set()], now) is False
    assert SimpleScheduler._match_cron([{0}, {1}, {6}, {8}, set()], now) is True
    assert SimpleScheduler._match_cron([{0}, {1}, {6}, {8}, {4}], now) is True   # 周四 py_wd=3 → cron_wd=4
    assert SimpleScheduler._match_cron([{0}, {1}, {6}, {8}, {1}], now) is False
    sunday = datetime(2026, 8, 2, 10, 0)  # 周日
    assert SimpleScheduler._match_cron([{0}, {10}, {2}, {8}, {0}], sunday) is True


def test_check_jobs_cron_dedup():
    calls = []
    s = SimpleScheduler()
    s._loop = asyncio.new_event_loop()
    try:
        s.add_cron_job("c", "* * * * *", lambda: calls.append(1))
        s._check_jobs()
        assert calls == [1]
        s._check_jobs()  # 同一分钟去重
        assert calls == [1]
        assert s._last_fired.get("c") == datetime.now().strftime("%Y%m%d%H%M")
    finally:
        s._loop.close()


def test_check_jobs_cron_no_match():
    calls = []
    s = SimpleScheduler()
    s.add_cron_job("c", "59 23 31 12 *", lambda: calls.append(1))  # 大概率不匹配
    s._check_jobs()
    assert calls == []


def test_check_jobs_interval_and_remove():
    calls = []
    s = SimpleScheduler()
    s._loop = asyncio.new_event_loop()
    try:
        s.add_interval_job("i", 30, lambda: calls.append(1))
        s._check_jobs()
        s._check_jobs()
        assert calls == [1, 1]
        s.remove_job("i")
        s._check_jobs()
        assert calls == [1, 1]
    finally:
        s._loop.close()


def test_check_jobs_exception_safe():
    def bad():
        raise RuntimeError("job boom")
    s = SimpleScheduler()
    s.add_cron_job("bad", "* * * * *", bad)
    s._check_jobs()  # 不抛


def test_fire_loop_none_and_sync():
    calls = []
    s = SimpleScheduler()
    s.add_interval_job("i", 1, lambda: calls.append(1))
    s._check_jobs()   # _loop is None → _fire 直接返回
    assert calls == []
    # 带 loop 的同步执行
    s._loop = asyncio.new_event_loop()
    try:
        s._check_jobs()
        assert calls == [1]
    finally:
        s._loop.close()


def test_fire_coroutine(monkeypatch):
    fired = []

    async def afunc(x):
        fired.append(x)

    s = SimpleScheduler()
    s.add_interval_job("c", 1, afunc, 42)
    s._loop = asyncio.new_event_loop()
    try:
        s._check_jobs()
        # task 已创建但未运行；手动跑一次事件循环让 task 完成
        s._loop.run_until_complete(asyncio.sleep(0))
        assert fired == [42]
    finally:
        s._loop.close()


def test_fire_func_exception():
    def bad():
        raise ValueError("x")
    s = SimpleScheduler()
    s.add_interval_job("b", 1, bad)
    s._loop = asyncio.new_event_loop()
    try:
        s._check_jobs()  # 不抛
    finally:
        s._loop.close()


def test_tick_loop(monkeypatch):
    import infra.schedule.simple_scheduler as ss_mod
    s = SimpleScheduler()
    s._running = True
    checked = []

    def fake_check():
        checked.append(1)
        s._running = False

    s._check_jobs = fake_check
    orig_sleep = asyncio.sleep
    monkeypatch.setattr(ss_mod.asyncio, "sleep", lambda x: orig_sleep(0))
    asyncio.run(s._tick_loop())
    assert checked == [1]


def test_tick_loop_exception(monkeypatch):
    import infra.schedule.simple_scheduler as ss_mod
    s = SimpleScheduler()
    s._running = True

    def fake_check():
        s._running = False
        raise RuntimeError("tick boom")

    s._check_jobs = fake_check
    orig_sleep = asyncio.sleep
    monkeypatch.setattr(ss_mod.asyncio, "sleep", lambda x: orig_sleep(0))
    asyncio.run(s._tick_loop())  # 不抛


def test_start_shutdown(monkeypatch):
    s = SimpleScheduler()
    s.start()
    assert s._running is True and s._thread is not None
    s.start()  # 已运行 → 直接返回
    # 等 loop 就绪
    for _ in range(50):
        if s._loop is not None:
            break
        time.sleep(0.02)
    assert s._loop is not None
    s.shutdown()
    assert s._running is False
    # 停掉后台事件循环，避免线程残留
    if s._loop is not None:
        s._loop.call_soon_threadsafe(s._loop.stop)
        s._thread.join(timeout=2)
    # 可再次启动
    s.start()
    assert s._running is True
    s.shutdown()
    if s._loop is not None:
        s._loop.call_soon_threadsafe(s._loop.stop)
        s._thread.join(timeout=2)


def test_get_next_run_time():
    s = SimpleScheduler()
    assert s.get_next_run_time("missing") is None
    s.add_interval_job("i", 10, lambda: None)
    assert s.get_next_run_time("i") is None
    s.add_cron_job("c", "0 1 * * *", lambda: None)
    nxt = s.get_next_run_time("c")
    assert nxt is not None and nxt.endswith("01:00:00")


def test_safe_await_error():
    async def bad():
        raise RuntimeError("coro boom")
    asyncio.run(SimpleScheduler()._safe_await("j", bad()))  # 不抛


# ═══════════════════════════════════════════════════════════════
# infra/trace/trace.py
# ═══════════════════════════════════════════════════════════════

def test_trace_id_generate_and_set():
    tid = generate_trace_id()
    assert len(tid) == 32
    assert all(c in "0123456789abcdef" for c in tid)
    assert set_trace_id("fixed-123") == "fixed-123"
    assert get_trace_id() == "fixed-123"


def test_trace_id_auto_generate():
    tid = set_trace_id()
    assert len(tid) == 32
    assert get_trace_id() == tid
    # 恢复默认上下文
    set_trace_id("")


def test_trace_middleware():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/ping")
    def ping():
        return {"trace": get_trace_id()}

    client = TestClient(app)
    r = client.get("/ping", headers={"X-Trace-ID": "incoming-abc"})
    assert r.headers["X-Trace-ID"] == "incoming-abc"
    assert r.json()["trace"] == "incoming-abc"
    # 无透传头 → 自动生成
    r2 = client.get("/ping")
    assert len(r2.headers["X-Trace-ID"]) == 32


# ═══════════════════════════════════════════════════════════════
# infra/db/session.py
# ═══════════════════════════════════════════════════════════════

def test_normalize_url():
    from infra.db.session import _PROJECT_ROOT as root
    out = _normalize_url("sqlite:///./x.db")
    assert out.startswith("sqlite:///")
    assert os.path.isabs(out.replace("sqlite:///", "", 1))
    assert out == f"sqlite:///{os.path.join(root, './x.db')}"
    abs_url = f"sqlite:///{os.path.join(root, 'abs.db')}"
    assert _normalize_url(abs_url) == abs_url
    mysql = "mysql+pymysql://u:p@h/db"
    assert _normalize_url(mysql) == mysql


def test_init_db_idempotent():
    init_db()
    init_db()  # 二次调用不报错


def test_get_db_yields_session():
    gen = get_db()
    db = next(gen)
    assert db is not None
    from sqlalchemy import text
    assert db.execute(text("SELECT 1")).scalar() == 1
    gen.close()


def test_engine_and_session_factory():
    assert engine is not None
    s = SessionLocal()
    try:
        assert s is not None
    finally:
        s.close()
    assert DATABASE_URL


# ═══════════════════════════════════════════════════════════════
# infra/vector/vector_store.py — 纯逻辑部分
# ═══════════════════════════════════════════════════════════════

def test_ngram_vector_basic():
    f = NGramEmbeddingFunction()
    vec = f._text_to_vector("hello world 安全 攻击")
    assert len(vec) == 128
    norm = sum(v * v for v in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6
    # 确定性
    assert f._text_to_vector("hello") == f._text_to_vector("hello")


def test_ngram_vector_empty_and_symbols():
    f = NGramEmbeddingFunction()
    assert f._text_to_vector("") == [0.0] * 128
    assert f._text_to_vector("!!!###@@@") == [0.0] * 128
    assert f._text_to_vector("123456") != [0.0] * 128  # 数字 n-gram 保留


def test_ngram_call_multi():
    f = NGramEmbeddingFunction()
    out = f(["hello", "世界"])
    assert len(out) == 2
    assert all(len(v) == 128 for v in out)


def test_embedding_cache():
    c = EmbeddingCache(maxsize=2)
    assert c.get("k") is None
    c.set("a", [1.0])
    c.set("b", [2.0])
    assert c.get("a") == [1.0]
    c.set("c", [3.0])  # 触发淘汰 a
    assert c.get("a") is None
    assert c.get("b") == [2.0] and c.get("c") == [3.0]
    c.clear()
    assert c.get("b") is None


def test_known_dimensions():
    assert KNOWN_DIMENSIONS["ngram_fallback"] == 128
    assert KNOWN_DIMENSIONS["BAAI/bge-large-zh-v1.5"] == 1024


@pytest.fixture(autouse=True)
def _reset_vector_state():
    vs_mod.VectorStore._shared_client = None
    vs_mod.VectorStore._shared_client_dir = None
    yield
    vs_mod.VectorStore._shared_client = None
    vs_mod.VectorStore._shared_client_dir = None


def test_get_embedding_function_named(monkeypatch):
    class _FakeBGE:
        def __init__(self, *a, **k):
            pass

    monkeypatch.setattr(vs_mod, "BGEEmbeddingFunction", _FakeBGE)
    f = get_embedding_function("BAAI/bge-small-zh-v1.5")
    assert isinstance(f, _FakeBGE)


def test_get_embedding_function_default_and_fallback(monkeypatch):
    calls = {"n": 0}

    class _FlakyBGE:
        def __init__(self, *a, **k):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise RuntimeError("no model")

    monkeypatch.setattr(vs_mod, "BGEEmbeddingFunction", _FlakyBGE)
    f = get_embedding_function(None)
    assert isinstance(f, NGramEmbeddingFunction)
    assert calls["n"] == 2  # 默认模型失败 → MiniLM 失败 → N-gram


def test_bge_check_compatibility(monkeypatch):
    assert BGEEmbeddingFunction._check_compatibility() is True  # keras3 + tf_keras 都在
    monkeypatch.setitem(sys.modules, "keras", None)
    assert BGEEmbeddingFunction._check_compatibility() is True  # 无 keras → 不受影响

    class _Keras3:
        __version__ = "3.5.0"

    monkeypatch.setitem(sys.modules, "keras", _Keras3())
    monkeypatch.setitem(sys.modules, "tf_keras", None)
    assert BGEEmbeddingFunction._check_compatibility() is False  # keras3 无 tf-keras


def test_bge_fallback_ngram(monkeypatch):
    monkeypatch.setattr(BGEEmbeddingFunction, "_st_available", None)
    b = BGEEmbeddingFunction("BAAI/bge-small-zh-v1.5")  # sentence_transformers 缺失 → N-gram 降级
    assert b._model is None
    out = b(["测试文本", "hello"])
    assert len(out) == 2 and all(len(v) == 128 for v in out)
    monkeypatch.setattr(BGEEmbeddingFunction, "_st_available", None)


def test_bge_load_model_success_and_call(monkeypatch):
    class _FakeST:
        def __init__(self, *a, **k):
            pass

        def get_sentence_embedding_dimension(self):
            return 8

        def encode(self, texts, **kw):
            return np.array([[0.1] * 8 for _ in texts])

    fake_mod = _types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = _FakeST
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
    monkeypatch.setattr(BGEEmbeddingFunction, "_st_available", True)

    b = BGEEmbeddingFunction("BAAI/bge-small-zh-v1.5")
    assert b._model is not None
    out = b(["hello", "world"])
    assert len(out) == 2 and len(out[0]) == 8
    assert isinstance(out, list)
    monkeypatch.setattr(BGEEmbeddingFunction, "_st_available", None)


def test_bge_load_model_failure_then_lightweight(monkeypatch):
    class _FakeST:
        def __init__(self, *a, **k):
            raise RuntimeError("download failed")

    fake_mod = _types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = _FakeST
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
    monkeypatch.setattr(BGEEmbeddingFunction, "_st_available", True)

    b = BGEEmbeddingFunction("BAAI/bge-large-zh-v1.5")
    assert b._model is None  # 轻量模型同样失败
    monkeypatch.setattr(BGEEmbeddingFunction, "_st_available", None)


def test_bge_try_lightweight_success(monkeypatch):
    class _FakeST:
        def __init__(self, *a, **k):
            pass

        def get_sentence_embedding_dimension(self):
            return 384

    fake_mod = _types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = _FakeST
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
    b = BGEEmbeddingFunction.__new__(BGEEmbeddingFunction)
    b._try_lightweight()
    assert b._model is not None


# ── VectorStore: 真实 ChromaDB 主路径 ──

def test_vectorstore_real_chroma(tmp_path, monkeypatch):
    monkeypatch.setattr(vs_mod, "get_embedding_function", lambda *a, **k: NGramEmbeddingFunction())
    vs = VectorStore(f"ut_coll_{uuid.uuid4().hex[:8]}", str(tmp_path))
    assert vs._collection is not None
    assert vs._client is not None
    vs.add_documents(["hello world 安全测试"], [{"src": "ut", "level": "high"}], ["id-1"])
    assert vs.count() == 1
    items = vs.similarity_search("hello world", k=5)
    assert len(items) >= 1
    it = items[0]
    assert it["id"] == "id-1"
    assert 0.0 <= it["score"] <= 1.0
    assert it["document"] == "hello world 安全测试"
    assert it["metadata"] == {"src": "ut", "level": "high"}
    vs.add_documents([], [], [])  # 空文档直接返回
    assert vs.count() == 1


def test_vectorstore_add_documents_error(tmp_path, monkeypatch):
    monkeypatch.setattr(vs_mod, "get_embedding_function", lambda *a, **k: NGramEmbeddingFunction())

    class _FailingColl:
        def add(self, **kw):
            raise RuntimeError("add failed")

    vs = VectorStore.__new__(VectorStore)
    vs._collection = _FailingColl()
    vs.add_documents(["x"], [{}], ["1"])  # 不抛


def test_vectorstore_similarity_fake_collection(monkeypatch):
    vs = VectorStore.__new__(VectorStore)
    vs._collection = None
    vs.embed_fn = NGramEmbeddingFunction()

    class _FakeColl:
        def query(self, query_texts, n_results):
            return {
                "ids": [["a", "b"]],
                "distances": [[0.5, 1.5]],
                "documents": [["docA", "docB"]],
                "metadatas": [[{"k": 1}, {"k": 2}]],
            }

    vs._collection = _FakeColl()
    items = vs.similarity_search("q", k=2, score_threshold=0.5)
    assert [i["id"] for i in items] == ["a"]
    assert items[0]["score"] == 0.75  # 1 - 0.5/2
    # 无阈值 → 全部返回
    assert len(vs.similarity_search("q", k=2)) == 2
    # 距离缺失分支
    vs._collection = type("C", (), {"query": lambda self, **kw: {"documents": [["d"]], "ids": [["x"]], "metadatas": [[]]}})()
    items2 = vs.similarity_search("q")
    assert items2[0]["score"] == 0.0
    # 异常 → []
    vs._collection = type("C", (), {"query": lambda self, **kw: (_ for _ in ()).throw(RuntimeError("query failed"))})()
    assert vs.similarity_search("q") == []


def test_vectorstore_count_error(monkeypatch):
    vs = VectorStore.__new__(VectorStore)
    vs._collection = type("C", (), {"count": lambda self: (_ for _ in ()).throw(RuntimeError("x"))})()
    assert vs.count() == 0


# ── VectorStore: 客户端初始化路径（fake client 覆盖降级/重建分支）──

def _make_fake_collection(count=0, query_error=None):
    class _FakeColl:
        def count(self):
            return count

        def query(self, **kw):
            if query_error:
                raise query_error
            return {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}

    return _FakeColl()


def test_init_client_rebuild_on_dimension_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(vs_mod, "get_embedding_function", lambda *a, **k: NGramEmbeddingFunction())
    deleted = []

    class _FakeClient:
        def get_collection(self, name, embedding_function=None):
            return _make_fake_collection(count=1, query_error=Exception("dimensionality mismatch"))

        def delete_collection(self, name):
            deleted.append(name)

        def create_collection(self, name, embedding_function=None):
            return _make_fake_collection()

    fake = _FakeClient()
    monkeypatch.setattr(VectorStore, "_get_or_create_shared_client", lambda cls, path: fake)
    vs = VectorStore("coll-x", str(tmp_path))
    assert deleted == ["coll-x"]
    assert vs._collection is not None


def test_init_client_reuse_existing_collection(tmp_path, monkeypatch):
    monkeypatch.setattr(vs_mod, "get_embedding_function", lambda *a, **k: NGramEmbeddingFunction())

    class _FakeClient:
        def get_collection(self, name, embedding_function=None):
            return _make_fake_collection(count=3)  # 查询成功 → 维度匹配

        def delete_collection(self, name):
            raise AssertionError("不应重建")

        def create_collection(self, name, embedding_function=None):
            raise AssertionError("不应重建")

    fake = _FakeClient()
    monkeypatch.setattr(VectorStore, "_get_or_create_shared_client", lambda cls, path: fake)
    vs = VectorStore("coll-y", str(tmp_path))
    assert vs._collection is not None


def test_init_client_exception_creates_new(tmp_path, monkeypatch):
    monkeypatch.setattr(vs_mod, "get_embedding_function", lambda *a, **k: NGramEmbeddingFunction())

    class _FakeClient:
        def get_collection(self, name, embedding_function=None):
            raise Exception("collection not found")

        def delete_collection(self, name):
            pass

        def create_collection(self, name, embedding_function=None):
            return _make_fake_collection()

    fake = _FakeClient()
    monkeypatch.setattr(VectorStore, "_get_or_create_shared_client", lambda cls, path: fake)
    vs = VectorStore("coll-z", str(tmp_path))
    assert vs._collection is not None


def test_init_client_runtime_error(tmp_path, monkeypatch):
    monkeypatch.setattr(vs_mod, "get_embedding_function", lambda *a, **k: NGramEmbeddingFunction())
    monkeypatch.setattr(VectorStore, "_get_or_create_shared_client", lambda cls, path: None)
    with pytest.raises(RuntimeError):
        VectorStore("coll-r", str(tmp_path))


def test_get_or_create_shared_client_reuse(monkeypatch):
    VectorStore._shared_client = "FAKE-CLIENT"
    VectorStore._shared_client_dir = "/tmp/x"
    try:
        assert VectorStore._get_or_create_shared_client("/tmp/x") == "FAKE-CLIENT"
        monkeypatch.setattr(VectorStore, "_try_create_client", lambda path: None)
        assert VectorStore._get_or_create_shared_client("/tmp/other") is None
    finally:
        VectorStore._shared_client = None
        VectorStore._shared_client_dir = None


def test_try_create_client_cleans_journal(tmp_path, monkeypatch):
    (tmp_path / "chroma.sqlite3-journal").write_text("junk")
    monkeypatch.setattr(vs_mod.chromadb, "PersistentClient", lambda **kw: "CLIENT-OK")
    assert VectorStore._try_create_client(str(tmp_path)) == "CLIENT-OK"


def test_try_create_client_remove_error(tmp_path, monkeypatch):
    (tmp_path / "chroma.sqlite3").write_text("junk")

    def _fail_remove(f):
        raise OSError("locked")

    monkeypatch.setattr(vs_mod.os, "remove", _fail_remove)
    assert VectorStore._try_create_client(str(tmp_path)) is None


def test_try_create_client_creation_error(tmp_path, monkeypatch):
    def _fail_client(**kw):
        raise RuntimeError("chroma init failed")

    monkeypatch.setattr(vs_mod.chromadb, "PersistentClient", _fail_client)
    assert VectorStore._try_create_client(str(tmp_path)) is None


def test_get_target_dimension(monkeypatch):
    vs = VectorStore.__new__(VectorStore)
    vs.embed_fn = NGramEmbeddingFunction()
    assert vs._get_target_dimension() == 128  # 试跑推断
    vs.embed_fn = type("E", (), {"__call__": lambda self, t: (_ for _ in ()).throw(RuntimeError("no"))})()
    assert vs._get_target_dimension() == 128  # 异常 → 默认


# ═══════════════════════════════════════════════════════════════
# infra/db/repositories.py
# ═══════════════════════════════════════════════════════════════

@pytest.fixture()
def db():
    """每个用例独立 session，失败后回滚，避免污染共享 MySQL"""
    init_db()
    s = SessionLocal()
    yield s
    try:
        s.rollback()
    except Exception:
        pass
    s.close()


# ── DataSourceConfigRepo ──

def test_datasource_repo_crud(db):
    name = _uniq("ut-ds")
    cfg = repos.DataSourceConfigRepo.create(db, name=name, type="SYSLOG", status="enabled",
                                            config_json={"path": "/tmp/x"}, description="d")
    assert cfg.id and cfg.status == "enabled"
    assert repos.DataSourceConfigRepo.get(db, cfg.id).id == cfg.id
    assert repos.DataSourceConfigRepo.get(db, 999999) is None
    assert repos.DataSourceConfigRepo.get_by_name(db, name).id == cfg.id
    assert repos.DataSourceConfigRepo.get_by_name(db, "nope-" + name) is None

    ids = [x.id for x in repos.DataSourceConfigRepo.list_all(db, type_filter="SYSLOG")]
    assert cfg.id in ids
    ids_all = [x.id for x in repos.DataSourceConfigRepo.list_all(db)]
    assert cfg.id in ids_all

    enabled = [x.id for x in repos.DataSourceConfigRepo.get_enabled(db, types=["SYSLOG"])]
    assert cfg.id in enabled
    enabled_all = [x.id for x in repos.DataSourceConfigRepo.get_enabled(db)]
    assert cfg.id in enabled_all

    updated = repos.DataSourceConfigRepo.update(db, cfg, description="改", status="enabled")
    assert updated.description == "改"
    toggled = repos.DataSourceConfigRepo.toggle(db, cfg)
    assert toggled.status == "disabled"
    toggled2 = repos.DataSourceConfigRepo.toggle(db, cfg)
    assert toggled2.status == "enabled"
    repos.DataSourceConfigRepo.delete(db, cfg)
    assert repos.DataSourceConfigRepo.get(db, cfg.id) is None


# ── RawEventRepo / StdEventRepo / AssetVulnRepo ──

def test_raw_event_repo(db):
    tid = int(time.time() * 1000) % 100000000
    assert repos.RawEventRepo.add_many(db, []) == 0
    n = repos.RawEventRepo.add_many(db, [
        {"source_type": "SYSLOG", "receive_time": "2026-08-01 10:00:00",
         "raw_content": "line1", "status": "OK", "task_id": tid},
        {"source_type": "SYSLOG", "receive_time": "2026-08-01 10:00:01",
         "raw_content": "line2", "status": "ERROR", "task_id": tid},
    ])
    assert n == 2
    assert repos.RawEventRepo.count_by_task(db, tid) == 2
    assert repos.RawEventRepo.count_by_task(db, tid, status="ERROR") == 1
    assert repos.RawEventRepo.count_by_task(db, tid, status="PENDING") == 0
    assert repos.RawEventRepo.count_by_task(db, 99999999) == 0


def test_std_event_repo(db):
    tid = (int(time.time() * 1000) % 100000000) + 1
    assert repos.StdEventRepo.add_many(db, []) == 0
    n = repos.StdEventRepo.add_many(db, [
        {"event_time": "2026-08-01 10:00:00", "source_type": "SYSLOG", "event_type": "LOGIN",
         "risk_level": "HIGH", "task_id": tid},
        {"event_time": "2026-08-01 10:00:01", "source_type": "SYSLOG", "event_type": "SCAN",
         "risk_level": "MEDIUM", "task_id": tid},
    ])
    assert n == 2
    assert repos.StdEventRepo.count_by_task(db, tid) == 2
    assert len(repos.StdEventRepo.list_by_task(db, tid)) == 2
    assert len(repos.StdEventRepo.list_by_task(db, tid, limit=1)) == 1
    repos.StdEventRepo.delete_by_task(db, tid)
    assert repos.StdEventRepo.count_by_task(db, tid) == 0


def test_asset_vuln_repo(db):
    assert repos.AssetVulnRepo.add_many(db, []) == 0
    n = repos.AssetVulnRepo.add_many(db, [
        {"asset_ip": "10.0.0.1", "vuln_name": "CVE-2026-0001", "cvss": 9.8, "risk_level": "HIGH"},
        {"asset_ip": "10.0.0.2", "vuln_name": "CVE-2026-0002", "cvss": 5.0, "risk_level": "MEDIUM"},
    ])
    assert n == 2
    assert len(repos.AssetVulnRepo.list_all(db)) >= 2
    assert len(repos.AssetVulnRepo.list_all(db, limit=1)) == 1
    repos.AssetVulnRepo.clear(db)
    assert repos.AssetVulnRepo.list_all(db) == []


# ── ReportTaskRepo ──

def test_report_task_repo(db):
    suf = _uniq("cycle")
    task = repos.ReportTaskRepo.create(db, cycle=suf, window_start="2026-08-01 00:00:00",
                                       window_end="2026-08-06 00:00:00", trace_id="tr-" + suf)
    assert task.id and task.status == "PENDING"
    assert repos.ReportTaskRepo.get(db, task.id).id == task.id
    assert repos.ReportTaskRepo.get(db, 999999) is None

    upd = repos.ReportTaskRepo.update(db, task, status="RUNNING", duration_ms=10)
    assert upd.status == "RUNNING" and upd.duration_ms == 10

    found = repos.ReportTaskRepo.find_existing(db, suf, "2026-08-01 00:00:00", "2026-08-06 00:00:00")
    assert found is not None and found.id == task.id
    assert repos.ReportTaskRepo.find_existing(db, suf, "2020-01-01 00:00:00", "2020-01-02 00:00:00") is None

    rows, total = repos.ReportTaskRepo.list_all(db, cycle=suf)
    assert total >= 1 and any(t.id == task.id for t in rows)
    rows2, total2 = repos.ReportTaskRepo.list_all(db, status="RUNNING", offset=0, limit=5)
    assert total2 >= 1
    rows3, total3 = repos.ReportTaskRepo.list_all(db, keyword=suf)
    assert any(t.id == task.id for t in rows3)
    rows4, _ = repos.ReportTaskRepo.list_all(db)
    assert isinstance(rows4, list)


# ── ReportVersionRepo ──

def test_report_version_repo(db):
    task = repos.ReportTaskRepo.create(db, cycle=_uniq("vcyc"), window_start="2026-08-01 00:00:00",
                                       window_end="2026-08-06 00:00:00")
    v1 = repos.ReportVersionRepo.create(db, task_id=task.id, cycle=task.cycle, version_no=1,
                                        window_start=task.window_start, window_end=task.window_end,
                                        title="初稿", content_md="# hi")
    v2 = repos.ReportVersionRepo.create(db, task_id=task.id, cycle=task.cycle, version_no=2,
                                        window_start=task.window_start, window_end=task.window_end,
                                        title="终稿", content_md="# bye")
    assert repos.ReportVersionRepo.get(db, v1.id).id == v1.id
    assert repos.ReportVersionRepo.get(db, 999999) is None
    lst = repos.ReportVersionRepo.list_by_task(db, task.id)
    assert [v.version_no for v in lst] == [2, 1]
    assert repos.ReportVersionRepo.get_latest_by_task(db, task.id).id == v2.id
    assert repos.ReportVersionRepo.get_latest_by_task(db, 999999) is None
    assert repos.ReportVersionRepo.next_version_no(db, task.id) == 3
    rows, total = repos.ReportVersionRepo.list_all(db, cycle=task.cycle)
    assert total >= 2
    rows2, total2 = repos.ReportVersionRepo.list_all(db, keyword="终稿")
    assert any(v.id == v2.id for v in rows2)
    rows3, _ = repos.ReportVersionRepo.list_all(db)
    assert isinstance(rows3, list)


# ── MetricSnapshotRepo ──

def test_metric_snapshot_repo(db):
    cyc = _uniq("ms")
    s1 = repos.MetricSnapshotRepo.create(db, task_id=1, cycle=cyc,
                                         window_start="2026-07-01 00:00:00", window_end="2026-08-01 00:00:00",
                                         metrics_json={"events": 100})
    s2 = repos.MetricSnapshotRepo.create(db, task_id=2, cycle=cyc,
                                         window_start="2026-08-01 00:00:00", window_end="2026-09-01 00:00:00",
                                         metrics_json={"events": 200})
    assert repos.MetricSnapshotRepo.get(db, s1.id).id == s1.id
    assert repos.MetricSnapshotRepo.get_by_task(db, 2).id == s2.id
    prev = repos.MetricSnapshotRepo.find_prev_snapshot(db, cyc, "2026-08-01 00:00:00", "2026-09-01 00:00:00")
    assert prev is not None and prev.id == s1.id
    assert repos.MetricSnapshotRepo.find_prev_snapshot(db, cyc, "2026-01-01 00:00:00", "2026-02-01 00:00:00") is None


# ── AuditLogRepo / PushLogRepo ──

def test_audit_log_repo(db):
    log = repos.AuditLogRepo.add(db, operator="ut-user", action="CREATE",
                                 target_type="REPORT", target_id=7, detail="d", client_ip="1.2.3.4", trace_id="t1")
    assert log.id and log.operator == "ut-user"
    log2 = repos.AuditLogRepo.add(db, operator="ut-user", action="DELETE")
    assert log2.target_type == "" and log2.target_id == 0
    all_logs = repos.AuditLogRepo.list_all(db)
    assert any(x.id == log.id for x in all_logs)
    filtered = repos.AuditLogRepo.list_all(db, target_type="REPORT", target_id=7)
    assert any(x.id == log.id for x in filtered)
    by_target = repos.AuditLogRepo.list_by_target(db, "REPORT", 7)
    assert any(x.id == log.id for x in by_target)
    limited = repos.AuditLogRepo.list_all(db, limit=1)
    assert len(limited) <= 1


def test_push_log_repo(db):
    p1 = repos.PushLogRepo.create(db, version_id=42, channel="email", status="PENDING", detail="d")
    p2 = repos.PushLogRepo.create(db, version_id=42, channel="dingtalk", status="SUCCESS")
    rows = repos.PushLogRepo.list_by_version(db, 42)
    assert {p.id for p in rows} >= {p1.id, p2.id}
    assert rows[0].id == p2.id  # id 倒序


# ── KnowledgeDocRepo ──

def test_knowledge_doc_repo(db):
    doc = repos.KnowledgeDocRepo.create(db, title=_uniq("ut-kb"), category="attack", content="SSH 爆破特征", enabled="enabled")
    assert doc.id
    assert repos.KnowledgeDocRepo.get(db, doc.id).id == doc.id
    assert repos.KnowledgeDocRepo.get(db, 999999) is None
    assert any(d.id == doc.id for d in repos.KnowledgeDocRepo.list_all(db, category="attack"))
    assert any(d.id == doc.id for d in repos.KnowledgeDocRepo.list_all(db))
    assert any(d.id == doc.id for d in repos.KnowledgeDocRepo.list_enabled(db))

    upd = repos.KnowledgeDocRepo.update(db, doc, title="改标题", content="新内容")
    assert upd.title == "改标题"
    t1 = repos.KnowledgeDocRepo.toggle(db, doc)
    assert t1.enabled == "disabled"
    t2 = repos.KnowledgeDocRepo.toggle(db, doc)
    assert t2.enabled == "enabled"
    repos.KnowledgeDocRepo.delete(db, doc)
    assert repos.KnowledgeDocRepo.get(db, doc.id) is None


# ── UserRepo ──

def test_user_repo_crud(db):
    uname = _uniq("ut-user")
    u = repos.UserRepo.create(db, username=uname, password_hash="pbkdf2$x", role="analyst", display_name="测试")
    assert u.id and u.enabled == "enabled"
    assert repos.UserRepo.get_by_username(db, uname).id == u.id
    assert repos.UserRepo.get_by_username(db, "no-" + uname) is None
    assert repos.UserRepo.get(db, u.id).id == u.id
    assert repos.UserRepo.get(db, 999999) is None
    assert any(x.id == u.id for x in repos.UserRepo.list_all(db))

    upd = repos.UserRepo.update(db, u, display_name="改名", role="admin")
    assert upd.display_name == "改名" and upd.role == "admin"
    assert upd.updated_at
    upd2 = repos.UserRepo.update(db, u, display_name=None)  # None 值跳过
    assert upd2.display_name == "改名"
    repos.UserRepo.delete(db, u)
    assert repos.UserRepo.get(db, u.id) is None


def test_user_repo_seed(db):
    repos.UserRepo.ensure_seed_users(db)
    assert repos.UserRepo.get_by_username(db, "admin") is not None
    assert repos.UserRepo.get_by_username(db, "analyst") is not None
    assert repos.UserRepo.get_by_username(db, "viewer") is not None
    # 幂等
    repos.UserRepo.ensure_seed_users(db)
    assert repos.UserRepo.get_by_username(db, "admin") is not None


# ── ReportConfigRepo ──

def test_report_config_repo(db):
    cfg = repos.ReportConfigRepo.get_or_create(db)
    assert cfg.id == 1
    assert "DAILY" in cfg.enabled_cycles and cfg.sections["overview"] is True
    cfg2 = repos.ReportConfigRepo.get_or_create(db)  # 复用
    assert cfg2.id == 1
    saved = repos.ReportConfigRepo.save(db, cfg, auto_generate="enabled", sections={"overview": False})
    assert saved.auto_generate == "enabled" and saved.sections == {"overview": False}
    # 恢复默认，避免影响其他用例
    repos.ReportConfigRepo.save(db, cfg,
                                auto_generate="disabled",
                                sections=dict(repos.ReportConfigRepo.DEFAULT_SECTIONS))
