"""V2.7 测试 — 趋势告警（安全指标环比突增检测）

规则：rule_key = trend_{cycle}_{metric}（如 trend_MONTHLY_alert_total）
评估：取该周期最近两期非空快照算环比增长率，> 阈值触发（复用审计+推送+防抖链路）
测试数据用 2099 年 MONTHLY 窗口（测试库 SQLite 隔离，不与任何真实窗口冲突）。
"""
import pytest

from infra.alert.alerter import Alerter
from infra.db.repositories import AlertRuleRepo
from infra.db.session import SessionLocal
from model.entity.entities import AlertRule, AuditLog, MetricSnapshot

TASK = 990002  # V2.7 趋势告警测试专用 task_id
RULE_KEY = "trend_MONTHLY_alert_total"


def _metrics(alert_total: int, alert_high: int = 0) -> dict:
    return {
        "alert": {"total": alert_total, "high": alert_high, "medium": 0,
                  "low": 0, "info": 0, "close_rate": 0.5, "by_type": {}, "by_day": []},
        "vuln": {"total": 1, "unfixed": 0, "fixed": 1, "ignored": 0,
                 "unfixed_high": 0, "close_rate": 1.0, "top_assets": []},
        "top": [], "trend": [],
        "raw": {"event_count": alert_total, "vuln_count": 1},
    }


def _snap(db, ws: str, we: str, alert_total: int) -> None:
    db.add(MetricSnapshot(task_id=TASK, cycle="MONTHLY",
                          window_start=ws, window_end=we,
                          metrics_json=_metrics(alert_total)))
    db.flush()


def _cleanup():
    db = SessionLocal()
    db.query(MetricSnapshot).filter(MetricSnapshot.task_id == TASK).delete()
    db.query(AlertRule).filter(AlertRule.rule_key.like("trend_%")).delete()
    # 清残留 FAILED 任务/告警痕迹：健康规则 enabled 时避免误触发污染断言
    from model.entity.entities import AuditLog, PushLog, ReportTask
    db.query(ReportTask).filter(ReportTask.status == "FAILED").delete()
    db.query(AuditLog).filter(AuditLog.action.like("ALERT_%")).delete()
    db.query(PushLog).delete()
    # 恢复健康规则默认 enabled：持久测试库跨会话共享，本文件把健康规则 disabled
    # 隔离评估，teardown 必须还原，否则 test_v24 的 ensure_seed_rules 不会重置 enabled
    AlertRuleRepo.ensure_seed_rules(db)
    for key in ("task_fail_count", "llm_fallback_rate", "push_fail_count"):
        r = AlertRuleRepo.get_by_key(db, key)
        if r:
            r.enabled = "enabled"
    db.commit()
    db.close()


def _enable_trend_rule(db, threshold: float) -> AlertRule:
    """启用趋势规则并停用健康规则（测试隔离：check_and_alert 只评估趋势规则）"""
    AlertRuleRepo.ensure_seed_rules(db)
    for key in ("task_fail_count", "llm_fallback_rate", "push_fail_count"):
        r = AlertRuleRepo.get_by_key(db, key)
        if r:
            r.enabled = "disabled"
    rule = AlertRuleRepo.get_by_key(db, RULE_KEY)
    rule.enabled = "enabled"
    rule.threshold = threshold
    db.commit()
    return rule


def _fresh_alerter() -> Alerter:
    a = Alerter()
    a._last_fire.clear()
    return a


@pytest.fixture(autouse=True)
def _restore_health_rules():
    """每个用例结束恢复默认状态（删测试数据 + 健康规则 enabled）：
    持久测试库跨会话共享，本文件把健康规则 disabled 隔离评估，
    不还原会污染后续 test_v24（其 ensure_seed_rules 不重置 enabled）"""
    yield
    _cleanup()


@pytest.fixture()
def trend_alert_data():
    """MONTHLY 两期非空快照：2099-01 (alert 100) → 2099-02 (alert 160)，环比 +60%"""
    db = SessionLocal()
    try:
        _cleanup()
        _snap(db, "2099-01-01 00:00:00", "2099-02-01 00:00:00", 100)
        _snap(db, "2099-02-01 00:00:00", "2099-03-01 00:00:00", 160)
        db.commit()
        yield
    finally:
        _cleanup()
        db.close()


# ═══════════ 评估器 ═══════════

def test_trend_growth_calc():
    """用例1：增长率 = (cur-prev)/prev，描述含环比百分比"""
    db = SessionLocal()
    try:
        _cleanup()
        _snap(db, "2099-01-01 00:00:00", "2099-02-01 00:00:00", 100)
        _snap(db, "2099-02-01 00:00:00", "2099-03-01 00:00:00", 160)
        db.commit()
        a = _fresh_alerter()
        growth, desc = a._eval_rule(db, RULE_KEY, 1)
        assert growth == pytest.approx(0.6)
        assert "160" in desc and "+60.0%" in desc
    finally:
        _cleanup()
        db.close()


def test_trend_trigger_fire():
    """用例2：环比 +60% > 阈值 50% → 触发（审计 + PushLog 落库）"""
    db = SessionLocal()
    try:
        _cleanup()
        _snap(db, "2099-01-01 00:00:00", "2099-02-01 00:00:00", 100)
        _snap(db, "2099-02-01 00:00:00", "2099-03-01 00:00:00", 160)
        _enable_trend_rule(db, 0.5)
        db.commit()
        db.close()

        fired = _fresh_alerter().check_and_alert()
        assert RULE_KEY in fired

        db = SessionLocal()
        logs = db.query(AuditLog).filter(AuditLog.action == f"ALERT_{RULE_KEY}").all()
        assert len(logs) >= 1
    finally:
        _cleanup()
        db.close()


def test_trend_not_exceeded():
    """用例3：增长率 ≤ 阈值 → 不触发"""
    db = SessionLocal()
    try:
        _cleanup()
        _snap(db, "2099-01-01 00:00:00", "2099-02-01 00:00:00", 100)
        _snap(db, "2099-02-01 00:00:00", "2099-03-01 00:00:00", 140)  # +40%
        _enable_trend_rule(db, 0.5)
        db.commit()
        db.close()
        assert _fresh_alerter().check_and_alert() == []
    finally:
        _cleanup()
        db.close()


def test_trend_no_baseline():
    """用例4：仅一期（无基准）→ 不评估不触发"""
    db = SessionLocal()
    try:
        _cleanup()
        _snap(db, "2099-01-01 00:00:00", "2099-02-01 00:00:00", 100)
        _enable_trend_rule(db, 0.5)
        db.commit()
        db.close()
        assert _fresh_alerter().check_and_alert() == []
    finally:
        _cleanup()
        db.close()


def test_trend_from_zero():
    """用例5：上期 0 → 本期 >0（从无到有）→ 必触发"""
    db = SessionLocal()
    try:
        _cleanup()
        _snap(db, "2099-01-01 00:00:00", "2099-02-01 00:00:00", 0)
        _snap(db, "2099-02-01 00:00:00", "2099-03-01 00:00:00", 30)
        _enable_trend_rule(db, 0.5)
        db.commit()
        db.close()
        fired = _fresh_alerter().check_and_alert()
        assert RULE_KEY in fired
    finally:
        _cleanup()
        db.close()


# ═══════════ 种子与热更新 ═══════════

def test_seed_rules_disabled_by_default():
    """用例6：趋势种子规则存在且默认 disabled（防首期无基准误报）"""
    db = SessionLocal()
    try:
        _cleanup()
        AlertRuleRepo.ensure_seed_rules(db)
        for key in ("trend_MONTHLY_alert_total", "trend_WEEKLY_alert_high"):
            rule = AlertRuleRepo.get_by_key(db, key)
            assert rule is not None and rule.enabled == "disabled"
    finally:
        _cleanup()
        db.close()


def test_trend_rule_hot_update():
    """用例7：DB 改阈值 → 立即生效（热读，无需重启）"""
    db = SessionLocal()
    try:
        _cleanup()
        _snap(db, "2099-01-01 00:00:00", "2099-02-01 00:00:00", 100)
        _snap(db, "2099-02-01 00:00:00", "2099-03-01 00:00:00", 160)  # +60%
        _enable_trend_rule(db, 0.5)
        db.commit()
        # 阈值改到 0.8（80%）→ +60% 不再触发
        rule = AlertRuleRepo.get_by_key(db, RULE_KEY)
        AlertRuleRepo.update(db, rule.id, threshold=0.8, enabled="enabled",
                             updated_by="ut")
        db.commit()
        db.close()
        assert _fresh_alerter().check_and_alert() == []
    finally:
        _cleanup()
        db.close()
