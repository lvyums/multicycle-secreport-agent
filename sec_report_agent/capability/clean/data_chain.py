"""清洗责任链 — 校验/去重降噪/归一化/分级/时间切片

设计：
- 每个 CleanHandler 处理一个环节，返回 StdEvent 表示通过，返回 None 表示丢弃
- CleanChain 按注册顺序串联，任一环节丢弃即终止（短路）
- 环节计数供指标统计（清洗前后数量对比）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from model.struct.structs import StdEvent


@dataclass
class CleanContext:
    """清洗上下文 — 跨环节共享的统计与配置"""
    task_id: int = 0
    cycle: str = ""
    window_start: str = ""
    window_end: str = ""
    stats: dict = field(default_factory=dict)  # 各环节丢弃计数


class CleanHandler(ABC):
    """清洗环节基类"""

    name: str = "handler"

    @abstractmethod
    def handle(self, event: StdEvent, ctx: CleanContext) -> Optional[StdEvent]:
        """处理单个事件；返回 None 表示该事件被丢弃"""
        ...


class CleanChain:
    """责任链编排器"""

    def __init__(self, handlers: Optional[list[CleanHandler]] = None):
        self._handlers: list[CleanHandler] = handlers or []

    def add(self, handler: CleanHandler) -> "CleanChain":
        self._handlers.append(handler)
        return self

    @property
    def handlers(self) -> list[CleanHandler]:
        return self._handlers

    def process(self, events: list[StdEvent], ctx: CleanContext) -> list[StdEvent]:
        """整批处理：每个事件依次过链，统计丢弃原因"""
        kept: list[StdEvent] = []
        for event in events:
            current = event
            for handler in self._handlers:
                current = handler.handle(current, ctx)
                if current is None:
                    ctx.stats[f"drop_{handler.name}"] = ctx.stats.get(f"drop_{handler.name}", 0) + 1
                    break
            if current is not None:
                kept.append(current)
        ctx.stats["input"] = len(events)
        ctx.stats["kept"] = len(kept)
        ctx.stats["dropped"] = len(events) - len(kept)
        return kept

    def process_one(self, event: StdEvent, ctx: CleanContext) -> Optional[StdEvent]:
        """单条处理（测试/增量场景）"""
        current = event
        for handler in self._handlers:
            current = handler.handle(current, ctx)
            if current is None:
                return None
        return current
