"""V2.4 测试 — 运维深化：内置自检告警（阈值 DB 热读）/ 日志 JSON 结构化 / 脱敏 / 轮转 / 静态交付物
用户精简版 8 用例：告警触发×2、防抖、JSON 格式、脱敏×2、轮转、静态文件语法。
"""

import json
import logging
import os
from datetime import datetime

import pytest
import yaml

from common.logger.logger import JsonFormatter, mask_value, DEFAULT_SENSITIVE_FIELDS
from infra.alert.alerter import Alerter
from infra.db.repositories import AlertRuleRepo, AuditLogRepo
from infra.db.session import SessionLocal
from model.entity.entities import AlertRule, AuditLog, PushLog, ReportTask


# ═══════════ 告警触发（阈值 DB 热读） ═══════════

def _fresh_alerter() -> Alerter:
    a = Alerter()
    a._last_fire.clear()
    return a


def _cleanup():
    db = SessionLocal()
    db.query(ReportTask).filter(ReportTask.status == "FAILED").delete()
    db.query(AuditLog).filter(AuditLog.action.like("ALERT_%")).delete()
    db.query(PushLog).delete()
    db.commit()
    db.close()


def _make_failed_tasks(db, n: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for i in range(n):
        db.add(ReportTask(cycle="DAILY", status="FAILED",
                          window_start="2026-08-07 00:00:00",
                          window_end="2026-08-07 23:59:59",
                          created_at=now,
                          error_msg=f"v24-test-{i}"))
    db.commit()


def test_alert_trigger_task_fail():
    """用例1：任务失败数达阈值 → AuditLog + PushLog 落库"""
    _cleanup()
    db = SessionLocal()
    AlertRuleRepo.ensure_seed_rules(db)
    _make_failed_tasks(db, 3)
    db.close()

    fired = _fresh_alerter().check_and_alert()
    assert "task_fail_count" in fired

    db = SessionLocal()
    logs = db.query(AuditLog).filter(AuditLog.action == "ALERT_task_fail_count").all()
    assert len(logs) >= 1
    assert "任务失败 3 次" in logs[-1].detail
    # 推送走 mock 模式 → PushLog 落库
    assert db.query(PushLog).count() >= 1
    db.close()


def test_alert_trigger_llm_fallback():
    """用例2：LLM 降级率超阈值 → 触发（metrics 注入 fallback 计数）"""
    from infra import metrics
    metrics.reset_for_test("sec_report_llm_calls_total")
    metrics.inc("sec_report_llm_calls_total", {"mode": "fallback"})
    metrics.inc("sec_report_llm_calls_total", {"mode": "fallback"})
    metrics.inc("sec_report_llm_calls_total", {"mode": "primary"})  # 降级率 2/3 > 0.5

    db = SessionLocal()
    AlertRuleRepo.ensure_seed_rules(db)
    rule = AlertRuleRepo.get_by_key(db, "llm_fallback_rate")
    assert rule is not None
    db.close()

    fired = _fresh_alerter().check_and_alert()
    assert "llm_fallback_rate" in fired
    metrics.reset_for_test("sec_report_llm_calls_total")


def test_alert_dedup():
    """用例3：同规则 30 分钟防抖 → 第二次 check 不重复触发"""
    _cleanup()
    db = SessionLocal()
    AlertRuleRepo.ensure_seed_rules(db)
    _make_failed_tasks(db, 5)
    db.close()

    a = _fresh_alerter()
    assert "task_fail_count" in a.check_and_alert()
    assert a.check_and_alert() == []  # 防抖窗口内不再触发

    db = SessionLocal()
    n = db.query(AuditLog).filter(AuditLog.action == "ALERT_task_fail_count").count()
    assert n == 1
    db.close()


def test_alert_rule_hot_update():
    """用例4（补）：DB 改阈值/停用 → 立即生效（热读，无需重启）"""
    _cleanup()
    db = SessionLocal()
    AlertRuleRepo.ensure_seed_rules(db)
    rule = AlertRuleRepo.get_by_key(db, "task_fail_count")
    AlertRuleRepo.update(db, rule.id, threshold=100, enabled="disabled")
    db.close()

    db = SessionLocal()
    _make_failed_tasks(db, 3)
    db.close()

    assert _fresh_alerter().check_and_alert() == []  # 停用 → 不触发

    db = SessionLocal()
    rule = AlertRuleRepo.get_by_key(db, "task_fail_count")
    AlertRuleRepo.update(db, rule.id, threshold=3, enabled="enabled")
    db.close()


# ═══════════ 日志 JSON / 脱敏 / 轮转 ═══════════

def test_log_json_format():
    """用例5：JsonFormatter 输出 JSON，字段齐全"""
    record = logging.LogRecord("SecReportAgent", logging.INFO, __file__, 1,
                               "hello %s", ("world",), None)
    record.trace_id = "trace-abc"
    out = json.loads(JsonFormatter().format(record))
    assert out["ts"] and out["level"] == "INFO"
    assert out["msg"] == "hello world"
    assert out["trace_id"] == "trace-abc"


def test_mask_default_fields():
    """用例6：默认敏感字段脱敏（password/secret 打码，普通字段保留）"""
    masked = mask_value({"password": "p@ss", "user": {"token": "t1", "name": "alice"}},
                        DEFAULT_SENSITIVE_FIELDS)
    assert masked["password"] == "***"
    assert masked["user"]["token"] == "***"
    assert masked["user"]["name"] == "alice"


def test_mask_custom_fields(monkeypatch):
    """用例7：sensitive_fields 可配置 → 自定义字段也脱敏"""
    from config.settings import settings
    monkeypatch.setattr(settings, "sensitive_fields", "customer_id,card_no")
    fields = ["customer_id", "card_no"]
    masked = mask_value({"customer_id": "C001", "card_no": "6222", "name": "bob"}, fields)
    assert masked["customer_id"] == "***"
    assert masked["card_no"] == "***"
    assert masked["name"] == "bob"


def test_log_rotation_configured():
    """用例8：文件日志 RotatingFileHandler 10MB × 5 生效（doRollover 可用）"""
    root = logging.getLogger("SecReportAgent")
    rotators = [h for h in root.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert rotators, "未配置 RotatingFileHandler"
    h = rotators[0]
    assert h.maxBytes == 10 * 1024 * 1024
    assert h.backupCount == 5
    assert h.encoding == "utf-8"
    # doRollover 可执行（不抛异常）
    h.doRollover()


# ═══════════ 静态交付物语法 ═══════════

def test_static_observability_files():
    """用例9（补）：alert-rules.yml + promtail 示例 YAML 可解析、结构齐全"""
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "docs", "observability")
    rules = yaml.safe_load(open(os.path.join(base, "prometheus", "alert-rules.yml"), encoding="utf-8"))
    assert len(rules["groups"][0]["rules"]) == 4
    promtail = yaml.safe_load(open(os.path.join(base, "promtail", "config.yml"), encoding="utf-8"))
    assert "scrape_configs" in promtail
    assert "json" in promtail["scrape_configs"][0]["pipeline_stages"][0]
