"""数据源适配器抽象 — 所有数据源统一 fetch 接口

数据流：fetch(窗口) → list[dict 原始事件] → RawEvent 落地 → 清洗链路
"""

from abc import ABC, abstractmethod
from typing import Optional

from model.entity.entities import DataSourceConfig
from model.enum.enums import DataSourceType


class DataSourceAdapter(ABC):
    """数据源适配器基类

    子类实现：type 类属性 + fetch + validate_config
    """

    type: str = ""  # DataSourceType 值

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.name = config.name

    @abstractmethod
    def fetch(self, window_start: str, window_end: str, task_id: int = 0) -> list[dict]:
        """拉取窗口内原始数据，返回 dict 列表（供 RawEvent 落地）"""
        ...

    def validate_config(self) -> list[str]:
        """校验配置完整性，返回错误信息列表（空 = 通过）"""
        return []

    def test_connection(self) -> tuple[bool, str]:
        """连通性测试（默认基于 validate_config + 尝试 fetch 一条）"""
        errors = self.validate_config()
        if errors:
            return False, "; ".join(errors)
        return True, "ok"

    def get_type_label(self) -> str:
        try:
            return DataSourceType(self.type).label
        except ValueError:
            return self.type

    def describe(self) -> dict:
        """适配器信息（供前端展示）"""
        return {
            "name": self.name,
            "type": self.type,
            "type_label": self.get_type_label(),
            "config": self.config.config_json,
            "status": self.config.status,
        }
