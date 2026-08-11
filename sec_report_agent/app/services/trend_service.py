"""趋势分析与报告时间轴服务（V2.6）

数据源（零新表）：
- metric_snapshot：每期报告生成自动落一条完整指标快照（同窗口重跑会多条）
- report_version：每期报告版本（metric_snapshot_id 关联快照）

核心规则：
- 同窗口去重取最新（重跑同窗口多条快照，只保留最新一条）
- 默认过滤 EMPTY 快照（alert.total==0 且 vuln.total==0 的空窗口不画进趋势）
- 序列按 window_end 升序（时间轴从左到右）
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.db.repositories import ReportVersionRepo
from model.entity.entities import MetricSnapshot
from model.enum.enums import ReportCycle


class TrendService:
    """趋势序列 + 时间线查询（V2.6）"""

    # ── 指标扁平化 ──────────────────────────────

    @staticmethod
    def _num(value, default: float = 0.0) -> float:
        """防御性数值转换（旧快照可能缺字段/为 None）"""
        try:
            return float(value if value is not None else default)
        except (TypeError, ValueError):
            return float(default)

    @classmethod
    def _parse_metrics(cls, metrics: dict) -> dict:
        """MetricSet.to_dict() -> 扁平趋势点（全部数值兜底 0）"""
        metrics = metrics or {}
        alert = metrics.get("alert") or {}
        vuln = metrics.get("vuln") or {}
        raw = metrics.get("raw") or {}
        # 事件数优先取 raw.event_count（by_day 求和）；旧快照缺失时兜底 alert.total
        event_count = cls._num(raw.get("event_count")) if raw else 0.0
        if not event_count:
            event_count = cls._num(alert.get("total"))
        return {
            "alertTotal": cls._num(alert.get("total")),
            "alertHigh": cls._num(alert.get("high")),
            "alertMedium": cls._num(alert.get("medium")),
            "alertLow": cls._num(alert.get("low")),
            "alertInfo": cls._num(alert.get("info")),
            "alertCloseRate": cls._num(alert.get("close_rate")),
            "vulnTotal": cls._num(vuln.get("total")),
            "vulnUnfixed": cls._num(vuln.get("unfixed")),
            "vulnUnfixedHigh": cls._num(vuln.get("unfixed_high")),
            "vulnCloseRate": cls._num(vuln.get("close_rate")),
            "eventCount": event_count,
        }

    @staticmethod
    def _is_empty(flat: dict) -> bool:
        """EMPTY 快照：无告警且无漏洞的空窗口（默认不画进趋势）"""
        return flat["alertTotal"] == 0 and flat["vulnTotal"] == 0

    @classmethod
    def _window_label(cls, cycle: str, ws: str, we: str) -> str:
        """窗口标签：日报 MM-DD / 周报 MM-DD~MM-DD / 月报/季报 YYYY-MM / 年报 YYYY

        兼容两种落库格式：'YYYY-MM-DD'（演示种子）与 'YYYY-MM-DD HH:MM:SS'（真实落库）
        """
        ws, we = (ws or "")[:10], (we or "")[:10]   # 统一截取日期部分
        if cycle == ReportCycle.DAILY.value:
            return ws[5:] if len(ws) >= 10 else (ws or "-")
        if cycle == ReportCycle.WEEKLY.value:
            a = ws[5:] if len(ws) >= 10 else ws
            b = we[5:] if len(we) >= 10 else we
            return f"{a}~{b}" if a and b else (a or "-")
        if cycle in (ReportCycle.MONTHLY.value, ReportCycle.QUARTERLY.value):
            return ws[:7] if len(ws) >= 7 else (ws or "-")
        if cycle == ReportCycle.YEARLY.value:
            return ws[:4] if len(ws) >= 4 else (ws or "-")
        return ws or "-"

    # ── 序列查询 ────────────────────────────────

    @classmethod
    def list_snapshots(cls, db: Session, cycle: str, limit: int = 12,
                       include_empty: bool = False) -> list[dict]:
        """同周期快照序列：窗口去重取最新 → 过滤 EMPTY → 升序"""
        # 冗余取 limit*8 条：同窗口重跑会多条、EMPTY 会被过滤
        rows = db.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.cycle == cycle)
            .order_by(MetricSnapshot.window_end.desc(), MetricSnapshot.id.desc())
            .limit(limit * 8)
        ).scalars().all()

        seen: set = set()
        points: list[dict] = []
        for snap in rows:
            # 窗口 key 归一化到日期部分：兼容 'YYYY-MM-DD' 与 'YYYY-MM-DD HH:MM:SS' 两种落库格式
            key = (snap.window_start[:10], snap.window_end[:10])
            if key in seen:      # 同窗口只留最新（排序保证第一条最新）
                continue
            seen.add(key)
            flat = cls._parse_metrics(snap.metrics_json)
            if not include_empty and cls._is_empty(flat):
                continue
            points.append({
                "label": cls._window_label(cycle, snap.window_start, snap.window_end),
                "windowStart": snap.window_start,
                "windowEnd": snap.window_end,
                "snapshotId": snap.id,
                "createdAt": snap.created_at,
                **flat,
            })
            if len(points) >= limit:
                break
        points.reverse()         # window_end 升序（时间轴从左到右）
        return points

    @classmethod
    def series(cls, db: Session, cycle: str, limit: int = 12,
               include_empty: bool = False) -> dict:
        """单周期趋势序列（图表数据源）"""
        try:
            cycle_label = ReportCycle(cycle).label
        except ValueError:
            cycle_label = cycle
        return {
            "cycle": cycle,
            "cycleLabel": cycle_label,
            "points": cls.list_snapshots(db, cycle, limit=limit, include_empty=include_empty),
        }

    @classmethod
    def all_cycles(cls, db: Session, limit: int = 12,
                   include_empty: bool = False) -> list[dict]:
        """五周期各取最近 N 点（Dashboard 总览用）"""
        return [cls.series(db, c.value, limit=limit, include_empty=include_empty)
                for c in ReportCycle]

    # ── 时间线查询 ──────────────────────────────

    @classmethod
    def timeline(cls, db: Session, cycle: Optional[str] = None,
                 limit: int = 50) -> dict:
        """报告时间轴：版本 × 指标摘要（按生成时间倒序）"""
        versions, total = ReportVersionRepo.list_all(db, cycle=cycle, offset=0, limit=limit)
        snap_ids = [v.metric_snapshot_id for v in versions if v.metric_snapshot_id]
        snap_map: dict = {}
        if snap_ids:
            snaps = db.execute(
                select(MetricSnapshot).where(MetricSnapshot.id.in_(snap_ids))
            ).scalars().all()
            snap_map = {s.id: s for s in snaps}
        items = []
        for v in versions:
            snap = snap_map.get(v.metric_snapshot_id)
            flat = cls._parse_metrics(snap.metrics_json) if snap else {}
            items.append({
                "versionId": v.id,
                "versionNo": v.version_no,
                "cycle": v.cycle,
                "windowStart": v.window_start,
                "windowEnd": v.window_end,
                "title": v.title or "",
                "status": v.status,
                "createdAt": v.created_at,
                "alertTotal": flat.get("alertTotal", 0),
                "alertHigh": flat.get("alertHigh", 0),
                "vulnTotal": flat.get("vulnTotal", 0),
                "eventCount": flat.get("eventCount", 0),
            })
        return {"total": total, "items": items}
