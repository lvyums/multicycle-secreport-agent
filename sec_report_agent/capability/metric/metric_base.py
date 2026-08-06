"""指标聚合基类 — 模板方法模式 + 缓存代理

设计：
- MetricTemplate.build() 固定骨架：告警 → 漏洞 → TOP → 趋势 → 组装
- 子类按周期实现各环节（日报/周报可轻量，月报全量，季/年报加同比）
- CachedMetricProxy 包装聚合器：同窗口同周期命中缓存直接返回（TTL 可配）
"""

from abc import ABC, abstractmethod
from typing import Optional

from model.struct.structs import MetricSet
from infra.cache.cache import get_cache


class MetricTemplate(ABC):
    """指标聚合模板方法"""

    cycle: str = ""

    def build(self, events: list, vulns: list, window_start: str, window_end: str) -> MetricSet:
        """模板方法：固定编排骨架，子类覆写各计算环节"""
        alert = self.calc_alert(events, window_start, window_end)
        vuln = self.calc_vuln(vulns, window_start, window_end)
        top = self.calc_top(events, window_start, window_end)
        trend = self.calc_trend(events, window_start, window_end)
        return self.assemble(alert, vuln, top, trend, window_start, window_end)

    @abstractmethod
    def calc_alert(self, events: list, window_start: str, window_end: str) -> dict:
        """告警指标：总量/高危/趋势/来源分布"""
        ...

    @abstractmethod
    def calc_vuln(self, vulns: list, window_start: str, window_end: str) -> dict:
        """漏洞指标：未修复高危/闭环率/TOP 资产"""
        ...

    @abstractmethod
    def calc_top(self, events: list, window_start: str, window_end: str) -> dict:
        """TOP 排行：攻击源/攻击类型/受害资产"""
        ...

    @abstractmethod
    def calc_trend(self, events: list, window_start: str, window_end: str) -> dict:
        """趋势指标：按天/周分布 + 环比同比（无历史返回空）"""
        ...

    def assemble(self, alert: dict, vuln: dict, top: dict, trend: dict,
                 window_start: str, window_end: str) -> MetricSet:
        """组装 MetricSet（可覆写补充 raw 快照）"""
        return MetricSet(
            cycle=self.cycle,
            window_start=window_start,
            window_end=window_end,
            alert=alert,
            vuln=vuln,
            top=top,
            trend=trend,
            raw={"event_count": 0, "vuln_count": 0},
        )


class CachedMetricProxy:
    """指标聚合缓存代理 — 同窗口同周期复用结果（防重复计算/防 LLM 重复调用）"""

    def __init__(self, aggregator: MetricTemplate, ttl: int = 3600):
        self._aggregator = aggregator
        self._ttl = ttl
        self._cache = get_cache()

    @property
    def aggregator(self) -> MetricTemplate:
        return self._aggregator

    def build(self, events: list, vulns: list, window_start: str, window_end: str) -> MetricSet:
        key = f"metric:{self._aggregator.cycle}:{window_start}:{window_end}"
        cached = self._cache.get(key)
        if cached is not None:
            return MetricSet(**cached)
        metric = self._aggregator.build(events, vulns, window_start, window_end)
        # 空结果不缓存（避免污染后续重跑）
        raw = metric.raw or {}
        if raw.get("event_count", 0) > 0 or raw.get("vuln_count", 0) > 0:
            self._cache.set(key, metric.to_dict(), ttl=self._ttl)
        return metric

    def invalidate(self, window_start: str, window_end: str):
        key = f"metric:{self._aggregator.cycle}:{window_start}:{window_end}"
        self._cache.delete(key)
