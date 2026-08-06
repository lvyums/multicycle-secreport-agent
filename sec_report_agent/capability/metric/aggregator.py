"""指标聚合器 — MetricTemplate 通用实现（cycle 参数化，V1.1 月报闭环复用）

聚合逻辑对五周期通用：告警总量/分级/闭环率/类型分布/按天分布/TOP排行/漏洞台账
"""

from collections import Counter, defaultdict
from typing import Optional

from capability.metric.metric_base import MetricTemplate
from model.struct.structs import MetricSet
from model.enum.enums import RiskLevel


class MetricAggregator(MetricTemplate):
    """通用指标聚合器"""

    def __init__(self, cycle: str):
        self.cycle = cycle

    # ── 告警指标 ──
    def calc_alert(self, events: list, window_start: str, window_end: str) -> dict:
        alert_events = [e for e in events if e.event_type != "vuln"]
        total = len(alert_events)
        if total == 0:
            return {"total": 0, "high": 0, "medium": 0, "low": 0, "info": 0,
                    "close_rate": 0.0, "by_type": {}, "by_day": {}}

        level_counter = Counter(e.risk_level for e in alert_events)
        closed = sum(1 for e in alert_events if e.status == "closed")
        by_type = dict(Counter(e.event_type for e in alert_events).most_common())
        by_day = self._day_distribution(alert_events)

        return {
            "total": total,
            "high": level_counter.get(RiskLevel.HIGH.value, 0),
            "medium": level_counter.get(RiskLevel.MEDIUM.value, 0),
            "low": level_counter.get(RiskLevel.LOW.value, 0),
            "info": level_counter.get(RiskLevel.INFO.value, 0),
            "close_rate": round(closed / total, 4),
            "by_type": by_type,
            "by_day": by_day,
        }

    # ── 漏洞指标 ──
    def calc_vuln(self, vulns: list, window_start: str, window_end: str) -> dict:
        if not vulns:
            return {"total": 0, "unfixed": 0, "fixed": 0, "ignored": 0,
                    "unfixed_high": 0, "close_rate": 0.0, "top_assets": []}
        total = len(vulns)
        status_counter = Counter(v.status for v in vulns)
        unfixed = status_counter.get("unfixed", 0)
        fixed = status_counter.get("fixed", 0)
        ignored = status_counter.get("ignored", 0)
        unfixed_high = sum(
            1 for v in vulns if v.status == "unfixed" and v.risk_level == RiskLevel.HIGH.value
        )
        close_rate = round(fixed / total, 4) if total else 0.0

        # 未修复 TOP 资产
        asset_unfixed: Counter = Counter()
        for v in vulns:
            if v.status == "unfixed":
                asset_unfixed[v.asset_ip or "unknown"] += 1
        top_assets = [{"asset_ip": ip, "count": cnt} for ip, cnt in asset_unfixed.most_common(5)]

        return {
            "total": total, "unfixed": unfixed, "fixed": fixed, "ignored": ignored,
            "unfixed_high": unfixed_high, "close_rate": close_rate, "top_assets": top_assets,
        }

    # ── TOP 排行 ──
    def calc_top(self, events: list, window_start: str, window_end: str) -> dict:
        alert_events = [e for e in events if e.event_type != "vuln"]
        src_counter: Counter = Counter(e.src_ip or "unknown" for e in alert_events)
        type_counter: Counter = Counter(e.event_type for e in alert_events)
        asset_counter: Counter = Counter(e.asset_ip or "unknown" for e in alert_events)

        return {
            "top_src": [{"ip": ip, "count": cnt} for ip, cnt in src_counter.most_common(5)],
            "top_type": [{"type": t, "count": cnt} for t, cnt in type_counter.most_common(5)],
            "top_asset": [{"asset": a, "count": cnt} for a, cnt in asset_counter.most_common(5)],
        }

    # ── 趋势 ──
    def calc_trend(self, events: list, window_start: str, window_end: str) -> dict:
        alert_events = [e for e in events if e.event_type != "vuln"]
        return {
            "by_day": self._day_distribution(alert_events),
            # V1.1 无历史数据源，环比/同比留空（后续从 MetricSnapshot 取上一周期）
            "compare": {},
        }

    def assemble(self, alert: dict, vuln: dict, top: dict, trend: dict,
                 window_start: str, window_end: str) -> MetricSet:
        metric = super().assemble(alert, vuln, top, trend, window_start, window_end)
        by_day = alert.get("by_day") or []
        event_count = sum(d.get("total", 0) for d in by_day) if by_day else alert.get("total", 0)
        metric.raw = {
            "event_count": event_count,
            "vuln_count": vuln.get("total", 0),
        }
        return metric

    # ── 工具 ──
    @staticmethod
    def _day_distribution(events: list) -> list[dict]:
        """按天分布 [{date, total, high}]（升序）"""
        day_total: Counter = Counter()
        day_high: Counter = Counter()
        for e in events:
            day = e.event_time[:10]
            day_total[day] += 1
            if e.risk_level == RiskLevel.HIGH.value:
                day_high[day] += 1
        return [
            {"date": d, "total": day_total[d], "high": day_high[d]}
            for d in sorted(day_total.keys())
        ]
