"""V2.7 测试 — 邮件推送 real 化（smtplib 标准库，零新增依赖）

- mock 模式行为不变（继承 _push_mock）
- real 模式：未配 SMTP 显式失败可诊断；配置齐全走 SMTP_SSL/STARTTLS 发送
- 测试用 fake smtplib 模块（monkeypatch），不真连外部 SMTP；settings 用
  monkeypatch 改属性，不碰 .env（避免污染整批测试）
"""
import pytest

from capability.push.push_strategy import PushStrategyFactory
from capability.push import webhook_strategies as wh
from config.settings import settings

TITLE = "月度网络安全态势报告"
BODY = "# 总体态势\n本期告警 120 起，环比 +20%。"


class _FakeSMTP:
    """fake smtplib.SMTP_SSL / SMTP：记录发送参数，可注入异常"""
    fail_on_send = False
    sent_all: list = []  # 类级记录（_smtp_send 内部实例无法直接取到）

    def __init__(self, *args, **kwargs):
        self.sent = []

    def login(self, user, password):
        self.login_args = (user, password)

    def starttls(self):
        pass

    def sendmail(self, from_addr, to_addrs, msg):
        if _FakeSMTP.fail_on_send:
            raise OSError("connection reset by peer")
        _FakeSMTP.sent_all.append((from_addr, to_addrs, msg))
        self.sent.append((from_addr, to_addrs, msg))

    def quit(self):
        pass


class _FakeSMTPModule:
    SMTP_SSL = _FakeSMTP
    SMTP = _FakeSMTP


@pytest.fixture()
def fake_smtp(monkeypatch):
    _FakeSMTP.sent_all = []
    _FakeSMTP.fail_on_send = False
    monkeypatch.setattr(wh, "smtplib", _FakeSMTPModule())
    return _FakeSMTPModule


@pytest.fixture()
def real_email_settings(monkeypatch):
    monkeypatch.setattr(settings, "push_mode", "real")
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_port", 465)
    monkeypatch.setattr(settings, "smtp_user", "report-bot@test.local")
    monkeypatch.setattr(settings, "smtp_password", "smtp-pass")
    monkeypatch.setattr(settings, "smtp_use_tls", True)
    monkeypatch.setattr(settings, "smtp_from", "")
    monkeypatch.setattr(settings, "email_recipients", "leader@test.local, sec@test.local")


def test_email_mock_mode_unchanged():
    """用例1：mock 模式 email 推送行为不变（模拟发送成功）"""
    st = PushStrategyFactory.get("email")
    res = st.push({"title": TITLE, "content_md": BODY})
    assert res.success is True
    assert "模拟发送到邮件成功" in res.detail


def test_email_real_no_config(monkeypatch):
    """用例2：real 模式未配 SMTP_HOST → 显式失败可诊断"""
    monkeypatch.setattr(settings, "push_mode", "real")
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "email_recipients", "")
    st = PushStrategyFactory.get("email")
    res = st.push({"title": TITLE, "content_md": BODY})
    assert res.success is False
    assert "SMTP_HOST" in res.detail


def test_email_real_send_success(fake_smtp, real_email_settings):
    """用例3：real 配置齐全 → SMTP_SSL + login + sendmail 被调，返回成功"""
    st = PushStrategyFactory.get("email")
    res = st.push({"title": TITLE, "content_md": BODY})
    assert res.success is True
    assert "SMTP 真实发送成功" in res.detail
    assert res.extra.get("recipients") == 2
    # 类级记录验证真实调用：发件人取 smtp_user，收件人逗号分隔解析
    assert len(_FakeSMTP.sent_all) == 1
    from_addr, to_addrs, msg = _FakeSMTP.sent_all[0]
    assert from_addr == "report-bot@test.local"
    assert to_addrs == ["leader@test.local", "sec@test.local"]
    assert "=?utf-8?" in msg  # 主题 UTF-8 Header 编码
    assert wh.smtplib.SMTP_SSL is _FakeSMTP  # 走 SSL 分支
    assert "text/html" in msg


def test_email_real_md_to_html():
    """用例4：极简 MD→HTML 渲染：标题 + 正文转义包裹"""
    out = wh._md_to_html("标题<险>", "告警 #1\n\t<未转义>")
    assert "<h2>标题&lt;险&gt;</h2>" in out
    assert "&lt;未转义&gt;" in out
    assert "<pre" in out


def test_email_real_smtp_failure_returns_fail(fake_smtp, real_email_settings):
    """用例5：SMTP 发送异常（retries=0 快速验证）→ 返回失败 + 异常信息"""
    _FakeSMTP.fail_on_send = True
    try:
        ok, detail = wh._smtp_send(TITLE, BODY, ["a@test.local"], retries=0)
        assert ok is False
        assert "OSError" in detail and "connection reset" in detail
    finally:
        _FakeSMTP.fail_on_send = False


def test_email_real_no_recipients(real_email_settings, monkeypatch):
    """用例6：real 配置了 host 但收件人为空 → 显式失败"""
    monkeypatch.setattr(settings, "email_recipients", "")
    st = PushStrategyFactory.get("email")
    res = st.push({"title": TITLE, "content_md": BODY})
    assert res.success is False
    assert "EMAIL_RECIPIENTS" in res.detail
