"""推送策略抽象 — 报告交付渠道统一接口 + 工厂

V1.1 仅 local（本地归档）；email/dingtalk/wecom 预留扩展
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PushResult:
    """推送结果"""
    success: bool
    channel: str
    detail: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"success": self.success, "channel": self.channel,
                "detail": self.detail, "extra": self.extra}


class PushStrategy(ABC):
    """推送策略基类"""

    channel: str = "local"

    @abstractmethod
    def push(self, version_info: dict, context: Optional[dict] = None) -> PushResult:
        """推送报告版本（version_info 含 version_id/title/file_path/content_md 等）"""
        ...


class PushStrategyFactory:
    """推送策略工厂 — 按渠道注册/获取"""

    _registry: dict[str, type[PushStrategy]] = {}

    @classmethod
    def register(cls, strategy_cls: type[PushStrategy]):
        cls._registry[strategy_cls.channel] = strategy_cls

    @classmethod
    def get(cls, channel: str) -> Optional[PushStrategy]:
        strategy_cls = cls._registry.get(channel)
        if not strategy_cls:
            raise ValueError(f"未注册的推送渠道: {channel}，可用: {list(cls._registry.keys())}")
        return strategy_cls()

    @classmethod
    def available_channels(cls) -> list[str]:
        return list(cls._registry.keys())
