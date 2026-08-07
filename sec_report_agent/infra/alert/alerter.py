"""内置自检告警器（V2.4）— 阈值 DB 热读，改阈值/开关无需重启

检查项（规则存 alert_rule 表，每轮从 DB 读）：
  - task_fail_count    最近 window_hours 任务 FAILED 数 ≥ threshold
  - llm_fallback_rate  最近 window_hours LLM fallback 占比 > threshold
  - push_fail_count    最近 window_hours 推送失败数 ≥ threshold
触发：AuditLog 记 ALERT_xxx + 复用推送策略发钉钉/企微（mock 记 PushLog）
防抖：同 rule_key 30 分钟不重复（内存记录）
"""

import asyncio
import time
from datetime import datetime, timedelta

from common.logger.logger import LogManager
from infra.db.repositories import AlertRuleRepo, AuditLogRepo, PushLogRepo
from infra.db.session import SessionLocal
from model.entity.entities import AuditLog, ReportTask, PushLog

logger = LogManager.get_logger()

DEDUP_SECONDS = 30 * 60  # 同规则 30 分钟防抖


class Alerter:
    def __init__(self):
        self._last_fire: dict[str, float] = {}
        self._stop = False

    # ── 检查入口（循环与测试共用，不依赖后台任务） ──

    def check_and_alert(self) -> list[str]:
        """执行一轮检查，返回本次触发的 rule_key 列表（防抖内不触发）"""
        fired: list[str] = []
        db = SessionLocal()
        try:
            rules = AlertRuleRepo.list_all(db)
            for rule in rules:
                if rule.enabled != "enabled":
                    continue
                value, desc = self._eval_rule(db, rule.rule_key, rule.window_hours)
                if value is None:
                    continue
                if self._exceeded(rule.rule_key, value, rule.threshold):
                    now = time.time()
                    if now - self._last_fire.get(rule.rule_key, 0) < DEDUP_SECONDS:
                        continue
                    self._last_fire[rule.rule_key] = now
                    self._fire(db, rule.rule_key, rule.name, value, desc)
                    fired.append(rule.rule_key)
        finally:
            db.close()
        return fired

    # ── 规则求值 ──

    def _eval_rule(self, db, rule_key: str, window_hours: int) -> tuple[float | None, str]:
        """返回 (当前值, 描述)。无数据可评估返回 (None, '')"""
        since = (datetime.now() - timedelta(hours=window_hours)).strftime("%Y-%m-%d %H:%M:%S")
        if rule_key == "task_fail_count":
            n = db.query(ReportTask).filter(
                ReportTask.status == "FAILED", ReportTask.created_at >= since
            ).count()
            return float(n), f"近{window_hours}h 任务失败 {n} 次"
        if rule_key == "push_fail_count":
            n = db.query(PushLog).filter(
                PushLog.status == "FAILED", PushLog.created_at >= since
            ).count()
            return float(n), f"近{window_hours}h 推送失败 {n} 次"
        if rule_key == "llm_fallback_rate":
            from infra import metrics
            snap = metrics.snapshot()
            bucket = snap["labeled"].get("sec_report_llm_calls_total", {})
            fall = sum(v for k, v in bucket.items() if "fallback" in k)
            total = sum(bucket.values())
            if total == 0:
                return None, ""
            rate = fall / total
            return rate, f"近{window_hours}h LLM 降级 {fall}/{total}"
        return None, ""

    @staticmethod
    def _exceeded(rule_key: str, value: float, threshold: float) -> bool:
        if rule_key == "llm_fallback_rate":
            return value > threshold
        return value >= threshold

    # ── 触发动作：审计 + 推送 ──

    def _fire(self, db, rule_key: str, name: str, value: float, desc: str) -> None:
        msg = f"[ALERT:{rule_key}] {name} 触发：{desc}"
        logger.warning(msg)
        AuditLogRepo.add(db, operator="system", action=f"ALERT_{rule_key}",
                         target_type="alert", target_id=0, detail=f"{name} {desc}")
        # 推送（复用 V2.3 策略；mock 模式记 PushLog 不真发）
        try:
            from capability.push.push_strategy import PushStrategyFactory
            from capability.push.webhook_strategies import (
                DingTalkPushStrategy, WeComPushStrategy, EmailPushStrategy,
            )
            from capability.push.local_strategy import LocalPushStrategy
            PushStrategyFactory.register(LocalPushStrategy)
            PushStrategyFactory.register(DingTalkPushStrategy)
            PushStrategyFactory.register(WeComPushStrategy)
            PushStrategyFactory.register(EmailPushStrategy)
            for channel in ("dingtalk", "wecom"):
                try:
                    st = PushStrategyFactory.get(channel)
                    result = st.push({"title": f"系统告警：{name}", "content_md": msg})
                    PushLogRepo.create(db, version_id=0, channel=channel,
                                       status="SUCCESS" if result.success else "FAILED",
                                       detail=f"[告警推送] {result.detail[:360]}")
                except Exception as e:  # noqa: BLE001 单个渠道失败不影响其他
                    logger.warning(f"[ALERT] 推送 {channel} 失败: {e}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[ALERT] 推送链路不可用: {e}")
        try:
            from infra import metrics
            metrics.inc("sec_report_alert_total", {"rule": rule_key})
        except Exception:  # noqa: BLE001
            pass

    # ── 后台循环（lifespan 启动） ──

    async def run_loop(self, interval_seconds: int = 300):
        logger.info(f"[ALERT] 告警器启动，检查间隔 {interval_seconds}s")
        while not self._stop:
            try:
                self.check_and_alert()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[ALERT] 检查异常: {e}")
            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break

    def stop(self):
        self._stop = True


_alerter = Alerter()


def get_alerter() -> Alerter:
    return _alerter
