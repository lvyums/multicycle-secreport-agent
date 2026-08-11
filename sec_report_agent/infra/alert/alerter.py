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
        if rule_key.startswith("trend_"):
            return self._eval_trend_rule(db, rule_key)
        return None, ""

    # ── 趋势告警求值（V2.7：安全指标环比突增） ──

    _TREND_METRIC_LABEL = {
        "alert_total": "告警量", "alert_high": "高危告警", "alert_medium": "中危告警",
        "vuln_total": "漏洞数", "vuln_unfixed": "未修复漏洞", "event_count": "事件量",
    }
    # TrendService._parse_metrics 返回驼峰 key，规则 metric 用下划线 → 映射取值
    _TREND_POINT_KEY = {
        "alert_total": "alertTotal", "alert_high": "alertHigh", "alert_medium": "alertMedium",
        "vuln_total": "vulnTotal", "vuln_unfixed": "vulnUnfixed", "event_count": "eventCount",
    }

    def _eval_trend_rule(self, db, rule_key: str) -> tuple[float | None, str]:
        """趋势规则：rule_key = trend_{cycle}_{metric}

        取该周期最近两期非空快照（升序），算环比增长率：
        - 不足两期 → 不评估（首期无基准）
        - 上期=0 且本期=0 → 不评估
        - 上期=0 且本期>0 → 返回 99999（"从无到有"显著信号，必触发）
        - 否则 growth = (cur - prev) / prev
        """
        parts = rule_key.split("_", 2)
        if len(parts) != 3:
            return None, ""
        _, cycle, metric = parts
        point_key = self._TREND_POINT_KEY.get(metric)
        if point_key is None:
            return None, ""
        try:
            from app.services.trend_service import TrendService
            points = TrendService.list_snapshots(db, cycle, limit=2, include_empty=False)
        except Exception as e:  # noqa: BLE001 趋势数据异常不阻塞告警器
            logger.warning(f"[ALERT] 趋势评估 {rule_key} 异常: {e}")
            return None, ""
        if len(points) < 2:
            return None, ""
        prev, cur = points[-2], points[-1]
        pv, cv = float(prev.get(point_key, 0.0)), float(cur.get(point_key, 0.0))
        if pv == 0 and cv == 0:
            return None, ""
        if pv == 0:
            growth = 99999.0
            desc = (f"{cycle} {self._TREND_METRIC_LABEL.get(metric, metric)} "
                    f"从无到有：{int(pv)} → {int(cv)}")
        else:
            growth = (cv - pv) / pv
            desc = (f"{cycle} {self._TREND_METRIC_LABEL.get(metric, metric)} "
                    f"{int(pv)} → {int(cv)}，环比 {growth * 100:+.1f}%")
        return growth, desc

    @staticmethod
    def _exceeded(rule_key: str, value: float, threshold: float) -> bool:
        if rule_key == "llm_fallback_rate" or rule_key.startswith("trend_"):
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
