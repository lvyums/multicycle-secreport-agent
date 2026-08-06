"""Webhook 渠道推送策略（stub）— 钉钉/企微/邮件

外网受限环境不真联网：校验版本内容 + 模拟发送，记录 PushLog。
生产环境将 push() 内部替换为真实 HTTP 调用（requests/httpx）。
"""

from typing import Optional

from capability.push.push_strategy import PushStrategy, PushResult
from common.logger.logger import LogManager

logger = LogManager.get_logger()

CHANNEL_LABEL = {
    "dingtalk": "钉钉群机器人",
    "wecom": "企业微信群机器人",
    "email": "邮件",
}


class _WebhookStubStrategy(PushStrategy):
    """渠道 stub 基类：模拟 webhook 发送"""

    channel = "dingtalk"

    def push(self, version_info: dict, context: Optional[dict] = None) -> PushResult:
        title = version_info.get("title") or ""
        content = version_info.get("content_md") or ""
        if not title and not content:
            return PushResult(success=False, channel=self.channel, detail="版本无内容可推送")
        # 模拟发送（stub）：摘要 + 长度截断
        summary = (content[:80].replace("\n", " ") + "…") if len(content) > 80 else content
        detail = (f"模拟发送到{CHANNEL_LABEL.get(self.channel, self.channel)}成功 "
                  f"(stub, 生产环境替换为真实 HTTP 调用): 标题={title}")
        logger.info(f"[PUSH:{self.channel}] {detail}")
        return PushResult(
            success=True, channel=self.channel,
            detail=detail, extra={"summary": summary, "mock": True},
        )


class DingTalkPushStrategy(_WebhookStubStrategy):
    """钉钉群机器人推送（stub）"""
    channel = "dingtalk"


class WeComPushStrategy(_WebhookStubStrategy):
    """企业微信群机器人推送（stub）"""
    channel = "wecom"


class EmailPushStrategy(_WebhookStubStrategy):
    """邮件推送（stub）"""
    channel = "email"
