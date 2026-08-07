"""Webhook 渠道推送策略 — 钉钉/企微/邮件

- mock 模式（默认，settings.push_mode=mock）：校验内容 + 模拟发送，记录 PushLog —— 测试/开发零外网
- real 模式（settings.push_mode=real）：真实 HTTP 发送，钉钉 HMAC-SHA256 加签、企微 key 加签，
  失败重试 2 次指数退避（0.3 * 3^n），PushLog 记录真实 HTTP 状态码/响应摘要
- email：仅 stub（未实现真实 SMTP，标注提示）

零新增依赖（urllib）。
"""

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from typing import Optional

from capability.push.push_strategy import PushStrategy, PushResult
from common.logger.logger import LogManager
from config.settings import settings

logger = LogManager.get_logger()

CHANNEL_LABEL = {
    "dingtalk": "钉钉群机器人",
    "wecom": "企业微信群机器人",
    "email": "邮件",
}


def _http_post_json(url: str, payload: dict, headers: dict | None = None,
                    timeout: int = 10, retries: int = 2) -> tuple[int, str]:
    """POST JSON，重试 2 次指数退避；返回 (http_status, response_body)"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    last_status, last_body = 0, ""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                last_status = resp.status
                last_body = resp.read().decode("utf-8", errors="replace")[:300]
                if last_status < 400:
                    return last_status, last_body
        except Exception as e:
            last_status = 0
            last_body = f"exception: {e}"
        if attempt < retries:
            time.sleep(0.3 * (3 ** attempt))
    return last_status, last_body


def _dingtalk_sign(timestamp_ms: str, secret: str) -> str:
    """钉钉加签：HMAC-SHA256(secret, timestamp\\nsecret) → base64 → urlencode"""
    string_to_sign = f"{timestamp_ms}\n{secret}"
    digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"),
                      hashlib.sha256).digest()
    return urllib.parse.quote_plus(base64.b64encode(digest))


def _wecom_sign(timestamp_ms: str, key: str) -> str:
    """企微加签：HMAC-SHA256(key, timestamp) → base64"""
    digest = hmac.new(key.encode("utf-8"), timestamp_ms.encode("utf-8"),
                      hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


class _WebhookStubStrategy(PushStrategy):
    """渠道推送基类：mock 模拟 / real 真实 HTTP，按 settings.push_mode 切换"""

    channel = "dingtalk"

    def push(self, version_info: dict, context: Optional[dict] = None) -> PushResult:
        title = version_info.get("title") or ""
        content = version_info.get("content_md") or ""
        if not title and not content:
            return PushResult(success=False, channel=self.channel, detail="版本无内容可推送")
        if settings.push_mode == "real":
            return self._push_real(title, content)
        return self._push_mock(title, content)

    # ── mock：模拟发送（测试/开发） ──
    def _push_mock(self, title: str, content: str) -> PushResult:
        summary = (content[:80].replace("\n", " ") + "…") if len(content) > 80 else content
        detail = (f"模拟发送到{CHANNEL_LABEL.get(self.channel, self.channel)}成功 "
                  f"(stub, push_mode=mock): 标题={title}")
        logger.info(f"[PUSH:{self.channel}] {detail}")
        try:
            from infra import metrics
            metrics.inc("sec_report_push_total",
                        {"channel": self.channel, "result": "success"})
        except Exception:
            pass
        return PushResult(
            success=True, channel=self.channel,
            detail=detail, extra={"summary": summary, "mock": True},
        )

    # ── real：真实 HTTP 发送 + 重试 ──
    def _push_real(self, title: str, content: str) -> PushResult:
        raise NotImplementedError("子类需实现 _push_real")


class DingTalkPushStrategy(_WebhookStubStrategy):
    channel = "dingtalk"

    def _push_real(self, title: str, content: str) -> PushResult:
        url = settings.dingtalk_webhook_url
        if not url:
            return PushResult(success=False, channel=self.channel,
                              detail="push_mode=real 但未配置 DINGTALK_WEBHOOK_URL")
        timestamp_ms = str(round(time.time() * 1000))
        if settings.dingtalk_webhook_secret:
            url = f"{url}&timestamp={timestamp_ms}&sign={_dingtalk_sign(timestamp_ms, settings.dingtalk_webhook_secret)}"
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title[:20], "text": f"### {title}\n\n{content[:4000]}"},
        }
        status, body = _http_post_json(url, payload)
        ok = 200 <= status < 400
        detail = (f"钉钉真实发送 {'成功' if ok else '失败'} HTTP {status}: {body[:120]}"
                  if status else f"钉钉真实发送失败(网络异常): {body[:120]}")
        logger.info(f"[PUSH:dingtalk] {detail}")
        try:
            from infra import metrics
            metrics.inc("sec_report_push_total",
                        {"channel": self.channel, "result": "success" if ok else "fail"})
        except Exception:
            pass
        return PushResult(success=ok, channel=self.channel,
                          detail=detail, extra={"http_status": status, "mock": False})


class WeComPushStrategy(_WebhookStubStrategy):
    channel = "wecom"

    def _push_real(self, title: str, content: str) -> PushResult:
        url = settings.wecom_webhook_url
        if not url:
            return PushResult(success=False, channel=self.channel,
                              detail="push_mode=real 但未配置 WECOM_WEBHOOK_URL")
        timestamp_ms = str(int(time.time()))
        if settings.wecom_webhook_key:
            url = (f"{url}&timestamp={timestamp_ms}&sign={_wecom_sign(timestamp_ms, settings.wecom_webhook_key)}")
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": f"### {title}\n\n{content[:4000]}"},
        }
        status, body = _http_post_json(url, payload)
        ok = 200 <= status < 400
        detail = (f"企微真实发送 {'成功' if ok else '失败'} HTTP {status}: {body[:120]}"
                  if status else f"企微真实发送失败(网络异常): {body[:120]}")
        logger.info(f"[PUSH:wecom] {detail}")
        try:
            from infra import metrics
            metrics.inc("sec_report_push_total",
                        {"channel": self.channel, "result": "success" if ok else "fail"})
        except Exception:
            pass
        return PushResult(success=ok, channel=self.channel,
                          detail=detail, extra={"http_status": status, "mock": False})


class EmailPushStrategy(_WebhookStubStrategy):
    channel = "email"

    def _push_real(self, title: str, content: str) -> PushResult:
        # 邮件 SMTP 未实现（需 smtplib + 邮件服务器配置），real 模式显式失败
        return PushResult(success=False, channel=self.channel,
                          detail="邮件渠道暂未实现真实 SMTP 发送，请使用钉钉/企微渠道")


# ── 注册到工厂 ──
from capability.push.push_strategy import PushStrategyFactory

PushStrategyFactory.register(DingTalkPushStrategy)
PushStrategyFactory.register(WeComPushStrategy)
PushStrategyFactory.register(EmailPushStrategy)
