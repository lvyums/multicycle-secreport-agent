"""数据源适配器工厂 — 按 DataSourceType 注册/获取适配器"""

from capability.adapter.adapter_base import DataSourceAdapter
from capability.adapter.syslog_adapter import SyslogAdapter
from capability.adapter.api_adapter import ApiAdapter
from capability.adapter.db_adapter import DbAdapter
from capability.adapter.excel_adapter import ExcelAdapter
from capability.adapter.intel_adapter import IntelAdapter
from capability.adapter.history_adapter import HistoryAdapter


class AdapterFactory:
    """适配器工厂：type → 适配器类"""

    _registry: dict[str, type[DataSourceAdapter]] = {}

    @classmethod
    def register(cls, adapter_cls: type[DataSourceAdapter]):
        cls._registry[adapter_cls.type] = adapter_cls

    @classmethod
    def get(cls, config) -> DataSourceAdapter:
        """根据数据源配置返回适配器实例"""
        adapter_cls = cls._registry.get(config.type)
        if not adapter_cls:
            raise ValueError(f"未注册的数据源类型: {config.type}，可用: {list(cls._registry.keys())}")
        return adapter_cls(config)

    @classmethod
    def available_types(cls) -> list[str]:
        return list(cls._registry.keys())


# 默认注册六类适配器
AdapterFactory.register(SyslogAdapter)
AdapterFactory.register(ApiAdapter)
AdapterFactory.register(DbAdapter)
AdapterFactory.register(ExcelAdapter)
AdapterFactory.register(IntelAdapter)
AdapterFactory.register(HistoryAdapter)
