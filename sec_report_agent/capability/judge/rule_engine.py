"""规则引擎 — 可插拔规则 + 综合风险等级判定（研判第一路）

设计：
- Rule 基类：evaluate 返回 RiskFlag 或 None
- RuleEngine：注册规则 → evaluate_all 全量评估 → 综合风险等级（取最高级）
- 内置默认规则：告警量超标 / 未修复高危漏洞超标 / 闭环率过低（阈值来自 settings）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from config.settings import settings
from common.logger.logger import LogManager
from model.struct.structs import MetricSet
from model.enum.enums import RiskLevel

logger = LogManager.get_logger()

LEVEL_ORDER = {RiskLevel.INFO.value: 0, RiskLevel.LOW.value: 1,
               RiskLevel.MEDIUM.value: 2, RiskLevel.HIGH.value: 3}


@dataclass
class RiskFlag:
    """规则命中标记"""
    rule_name: str
    level: str                # RiskLevel
    message: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rule_name": self.rule_name,
            "level": self.level,
            "message": self.message,
            "evidence": self.evidence,
        }


class Rule(ABC):
    """规则基类"""

    name: str = "rule"
    description: str = ""

    @abstractmethod
    def evaluate(self, metric: MetricSet, context: dict) -> Optional[RiskFlag]:
        """评估指标，命中返回 RiskFlag，未命中返回 None"""
        ...


class RuleEngine:
    """规则引擎 — 规则注册 + 批量评估"""

    def __init__(self, rules: Optional[list[Rule]] = None):
        self._rules: list[Rule] = rules or []

    def register(self, rule: Rule):
        self._rules.append(rule)
        logger.info(f"[RULE] 注册规则: {rule.name}")

    @property
    def rules(self) -> list[Rule]:
        return self._rules

    def evaluate_all(self, metric: MetricSet, context: Optional[dict] = None) -> list[RiskFlag]:
        """评估全部规则，返回命中的风险标记列表"""
        context = context or {}
        flags: list[RiskFlag] = []
        for rule in self._rules:
            try:
                flag = rule.evaluate(metric, context)
                if flag:
                    flags.append(flag)
                    logger.info(f"[RULE] 命中 {rule.name}: {flag.message} (level={flag.level})")
            except Exception as e:
                logger.error(f"[RULE] 规则 {rule.name} 执行异常: {e}")
        return flags

    def composite_level(self, flags: list[RiskFlag]) -> str:
        """综合风险等级：取命中最高的规则等级；无命中返回 LOW"""
        if not flags:
            return RiskLevel.LOW.value
        return max(flags, key=lambda f: LEVEL_ORDER.get(f.level, 0)).level


# ═══════════ 内置默认规则 ═══════════

class AlertVolumeRule(Rule):
    """告警量超标规则"""

    name = "alert_volume"
    description = "窗口内告警总量超过阈值判定为高危态势"

    def evaluate(self, metric: MetricSet, context: dict) -> Optional[RiskFlag]:
        total = (metric.alert.get("total") or 0)
        threshold = settings.risk_high_alert_threshold
        if total > threshold:
            return RiskFlag(
                rule_name=self.name,
                level=RiskLevel.HIGH.value,
                message=f"告警总量 {total} 超过高危阈值 {threshold}",
                evidence={"total": total, "threshold": threshold},
            )
        return None


class UnfixedVulnRule(Rule):
    """未修复高危漏洞超标规则"""

    name = "unfixed_high_vuln"
    description = "未修复高危漏洞数量超过阈值判定为高危"

    def evaluate(self, metric: MetricSet, context: dict) -> Optional[RiskFlag]:
        unfixed = (metric.vuln.get("unfixed_high") or 0)
        threshold = settings.risk_high_vuln_unfixed_threshold
        if unfixed > threshold:
            return RiskFlag(
                rule_name=self.name,
                level=RiskLevel.HIGH.value,
                message=f"未修复高危漏洞 {unfixed} 个，超过阈值 {threshold}",
                evidence={"unfixed_high": unfixed, "threshold": threshold},
            )
        return None


class LowCloseRateRule(Rule):
    """闭环率过低规则"""

    name = "low_close_rate"
    description = "事件闭环率低于阈值判定为中危"

    def evaluate(self, metric: MetricSet, context: dict) -> Optional[RiskFlag]:
        close_rate = metric.alert.get("close_rate")
        threshold = settings.risk_closed_rate_threshold
        if close_rate is not None and close_rate < threshold:
            return RiskFlag(
                rule_name=self.name,
                level=RiskLevel.MEDIUM.value,
                message=f"事件闭环率 {close_rate:.1%} 低于阈值 {threshold:.0%}",
                evidence={"close_rate": close_rate, "threshold": threshold},
            )
        return None


def build_default_engine() -> RuleEngine:
    """构建带默认规则的引擎"""
    engine = RuleEngine()
    engine.register(AlertVolumeRule())
    engine.register(UnfixedVulnRule())
    engine.register(LowCloseRateRule())
    return engine
