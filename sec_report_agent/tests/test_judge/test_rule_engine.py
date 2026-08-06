"""规则引擎测试 — 可插拔规则 + 综合风险等级"""
import sys
sys.path.insert(0, ".")

from capability.judge.rule_engine import RuleEngine, RiskFlag, Rule, build_default_engine
from model.struct.structs import MetricSet


class AlwaysFlagRule(Rule):
    name = "test_always"
    description = "总是命中"

    def evaluate(self, metric, context):
        return RiskFlag(rule_name=self.name, level="HIGH", message="测试命中", evidence={"k": 1})


class NeverRule(Rule):
    name = "test_never"
    description = "永不命中"

    def evaluate(self, metric, context):
        return None


def _metric(total=0, close_rate=1.0, unfixed_high=0):
    return MetricSet(
        cycle="MONTHLY", window_start="2026-07-01", window_end="2026-08-01",
        alert={"total": total, "high": 0, "close_rate": close_rate},
        vuln={"unfixed_high": unfixed_high, "total": 0, "close_rate": 1.0},
        top={}, trend={}, raw={"event_count": total},
    )


def test_rule_engine_flags():
    engine = RuleEngine()
    engine.register(AlwaysFlagRule())
    engine.register(NeverRule())
    flags = engine.evaluate_all(_metric(total=50))
    assert len(flags) == 1
    assert flags[0].rule_name == "test_always"
    assert engine.composite_level(flags) == "HIGH"


def test_composite_level_empty():
    engine = RuleEngine()
    assert engine.composite_level([]) == "LOW"


def test_builtin_alert_volume_rule():
    engine = build_default_engine()
    flags = engine.evaluate_all(_metric(total=500))
    names = [f.rule_name for f in flags]
    assert "alert_volume" in names
    # 低量不命中
    assert len(engine.evaluate_all(_metric(total=5))) == 0


def test_builtin_low_close_rate_rule():
    engine = build_default_engine()
    flags = engine.evaluate_all(_metric(total=10, close_rate=0.3))
    assert any(f.rule_name == "low_close_rate" for f in flags)


def test_builtin_unfixed_high_vuln_rule():
    engine = build_default_engine()
    flags = engine.evaluate_all(_metric(total=10, unfixed_high=20))
    assert any(f.rule_name == "unfixed_high_vuln" for f in flags)
