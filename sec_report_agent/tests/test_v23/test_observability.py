"""V2.3 测试 — 运维完善：可观测性(/health 就绪探针 /metrics) / 推送 real 模式 / 导出审计 / 审计端点权限
覆盖 A 可观测性、B 推送真实化、C 审计补全的关键路径。
"""

import base64
import hashlib
import hmac
import urllib.parse

import pytest

from api.auth_deps import get_current_user
from infra.cache.cache import MemoryCache
from infra.db.session import SessionLocal
from infra.db.repositories import AuditLogRepo
from model.entity.entities import AuditLog, ReportVersion


# ── 工具 ──

def _uniq(prefix: str) -> str:
    import time
    return f"{prefix}_{int(time.time() * 1000)}"


@pytest.fixture
def admin_user(rbac_override):
    return rbac_override("admin")


@pytest.fixture
def viewer_user(rbac_override):
    return rbac_override("viewer")


# ── A 可观测性 ──

def test_health_readiness_probe(client):
    """就绪探针：依赖明细全 ok，返回 status=ok"""
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["status"] == "ok"
    for dep in ("db", "cache", "vector"):
        assert d["checks"][dep] == "ok"


def test_metrics_endpoint_format(client):
    """Prometheus 文本格式：HELP/TYPE/指标名齐全"""
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    assert "# HELP sec_report_task_total" in body
    assert "# TYPE sec_report_task_total counter" in body
    assert "# HELP sec_report_llm_calls_total" in body
    assert "# HELP sec_report_push_total" in body


def test_metrics_counter_increment(client, admin_user):
    """埋点生效：任务终态计数增加"""
    from infra import metrics
    metrics.reset_for_test("sec_report_task_total")
    from infra.metrics import inc
    inc("sec_report_task_total", {"status": "DONE"})
    body = client.get("/metrics").text
    assert 'sec_report_task_total{status="DONE"} 1' in body


def test_health_degraded_when_cache_down(client, monkeypatch):
    """缓存依赖挂 → /health 503 degraded（就绪探针摘流量）"""
    from main import _check_cache
    monkeypatch.setattr("main._check_cache", lambda: (False, "fail: boom"))
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["data"]["status"] == "degraded"
    assert "cache" in r.json()["data"]["checks"]


# ── B 推送 real 模式 ──

def test_push_real_dingtalk_success(client, monkeypatch):
    """钉钉 real：签名参数正确 + HTTP 200 → PushResult success"""
    from capability.push import webhook_strategies as ws
    from config.settings import settings
    monkeypatch.setattr(settings, "push_mode", "real")
    monkeypatch.setattr(settings, "dingtalk_webhook_url", "https://oapi.dingtalk.com/robot/send?access_token=test")
    monkeypatch.setattr(settings, "dingtalk_webhook_secret", "SEC123")

    captured = {}

    def fake_post(url, payload, headers=None, timeout=10, retries=2):
        captured["url"] = url
        captured["payload"] = payload
        return 200, '{"errcode":0}'

    monkeypatch.setattr(ws, "_http_post_json", fake_post)
    st = ws.PushStrategyFactory.get("dingtalk")
    r = st.push({"title": "测试报告", "content_md": "# 报告\n内容"})
    assert r.success
    # 签名参数：timestamp + sign
    assert "timestamp=" in captured["url"]
    assert "sign=" in captured["url"]
    # 验签：用同样算法重算对比
    qs = urllib.parse.urlparse(captured["url"]).query
    params = dict(urllib.parse.parse_qsl(qs))
    string_to_sign = f"{params['timestamp']}\nSEC123"
    digest = hmac.new(b"SEC123", string_to_sign.encode(), hashlib.sha256).digest()
    # parse_qsl 已解码 %3D → sign 是原始 base64
    expect = base64.b64encode(digest).decode()
    assert params["sign"] == expect
    assert captured["payload"]["msgtype"] == "markdown"


def test_push_real_wecom_success(client, monkeypatch):
    """企微 real：签名 + markdown payload"""
    from capability.push import webhook_strategies as ws
    from config.settings import settings
    monkeypatch.setattr(settings, "push_mode", "real")
    monkeypatch.setattr(settings, "wecom_webhook_url", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test")
    monkeypatch.setattr(settings, "wecom_webhook_key", "KEY9")

    captured = {}

    def fake_post(url, payload, headers=None, timeout=10, retries=2):
        captured["url"] = url
        captured["payload"] = payload
        return 200, "ok"

    monkeypatch.setattr(ws, "_http_post_json", fake_post)
    st = ws.PushStrategyFactory.get("wecom")
    r = st.push({"title": "周报", "content_md": "内容"})
    assert r.success
    assert "sign=" in captured["url"]
    assert captured["payload"]["msgtype"] == "markdown"


def test_push_real_dingtalk_no_webhook(client, monkeypatch):
    """real 模式但未配置 webhook → 显式失败（配置缺失可诊断）"""
    from capability.push import webhook_strategies as ws
    from config.settings import settings
    monkeypatch.setattr(settings, "push_mode", "real")
    monkeypatch.setattr(settings, "dingtalk_webhook_url", "")
    st = ws.PushStrategyFactory.get("dingtalk")
    r = st.push({"title": "t", "content_md": "c"})
    assert not r.success
    assert "DINGTALK_WEBHOOK_URL" in r.detail


def test_push_mock_mode_unchanged(client):
    """mock 模式（默认）行为不变：模拟成功 + mock=True"""
    from capability.push import webhook_strategies as ws
    st = ws.PushStrategyFactory.get("dingtalk")
    r = st.push({"title": "t", "content_md": "c"})
    assert r.success
    assert r.extra.get("mock") is True


# ── C 审计补全 ──

def test_audit_logs_endpoint_admin_ok(client, admin_user):
    """审计端点：admin 可访问"""
    r = client.get("/api/auth/audit-logs?limit=5")
    assert r.status_code == 200
    assert "items" in r.json()["data"]


def test_audit_logs_endpoint_viewer_forbidden(client, viewer_user):
    """审计端点：viewer 403"""
    r2 = client.get("/api/auth/audit-logs")
    assert r2.status_code == 403


def test_export_writes_audit_log(client, admin_user):
    """导出报告 → 审计 EXPORT_REPORT 留痕（操作者/版本/格式）"""
    # 造一个版本
    db = SessionLocal()
    try:
        from infra.db.repositories import ReportTaskRepo
        task = ReportTaskRepo.create(db, cycle="DAILY", status="DONE",
                                     window_start="2026-08-01 00:00:00",
                                     window_end="2026-08-01 23:59:59")
        version = ReportVersion(task_id=task.id, version_no=1, status="PUBLISHED",
                                cycle="DAILY", window_start="2026-08-01 00:00:00",
                                window_end="2026-08-01 23:59:59",
                                title="V2.3 导出审计报告", content_md="# 内容")
        db.add(version)
        db.commit()
        vid = version.id
    finally:
        db.close()

    r = client.get(f"/api/report/export/{vid}?format=md")
    assert r.status_code == 200

    db = SessionLocal()
    try:
        logs = db.query(AuditLog).filter(
            AuditLog.action == "EXPORT_REPORT",
            AuditLog.target_id == vid,
        ).all()
        assert len(logs) >= 1
        assert logs[-1].operator == admin_user.username
        assert "MD" in logs[-1].detail
    finally:
        db.close()


def test_metrics_push_counter(client, monkeypatch):
    """推送埋点：mock 成功后 sec_report_push_total 计数"""
    from infra import metrics
    metrics.reset_for_test("sec_report_push_total")
    from capability.push import webhook_strategies as ws
    st = ws.PushStrategyFactory.get("dingtalk")
    st.push({"title": "t", "content_md": "c"})
    body = client.get("/metrics").text
    assert 'sec_report_push_total{channel="dingtalk",result="success"} 1' in body
