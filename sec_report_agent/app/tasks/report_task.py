"""报告任务执行入口 — 周期窗口计算 + 全链路编排（D2 阶段接入完整 pipeline）

V1.0 占位：仅计算窗口并记录日志，B/C/D 阶段填充各环节。
"""

from datetime import datetime, timedelta

from common.logger.logger import LogManager
from model.enum.enums import ReportCycle

logger = LogManager.get_logger()


def calc_window(cycle: str, ref: datetime | None = None) -> tuple[str, str]:
    """计算指定周期的统计窗口（前闭后开）

    日:   昨日 00:00 → 今日 00:00
    周:   上周一 00:00 → 本周一 00:00
    月:   上月 1 日 → 本月 1 日
    季:   上季度首日 → 本季度首日
    年:   去年 1 月 1 日 → 今年 1 月 1 日
    """
    ref = ref or datetime.now()
    today = datetime(ref.year, ref.month, ref.day)

    if cycle == ReportCycle.DAILY.value:
        end = today
        start = today - timedelta(days=1)
    elif cycle == ReportCycle.WEEKLY.value:
        end = today - timedelta(days=today.weekday())          # 本周一
        start = end - timedelta(days=7)
    elif cycle == ReportCycle.MONTHLY.value:
        end = datetime(ref.year, ref.month, 1)
        start = (end - timedelta(days=1)).replace(day=1)
    elif cycle == ReportCycle.QUARTERLY.value:
        end = datetime(ref.year, ((ref.month - 1) // 3) * 3 + 1, 1)
        start = datetime(ref.year, ((ref.month - 4) % 12) // 3 * 3 + 1, 1)
        if start > end:
            start = datetime(ref.year - 1, 10, 1)
    elif cycle == ReportCycle.YEARLY.value:
        end = datetime(ref.year, 1, 1)
        start = datetime(ref.year - 1, 1, 1)
    else:
        raise ValueError(f"未知周期: {cycle}")

    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def run_report_task(cycle: str, trigger_type: str = "MANUAL",
                    window_start: str | None = None, window_end: str | None = None) -> dict:
    """报告任务入口：创建任务 + 编排 pipeline（V1.0 占位）"""
    from infra.db.session import SessionLocal
    from infra.db.repositories import ReportTaskRepo
    from infra.trace.trace import set_trace_id, get_trace_id

    set_trace_id()
    if not window_start or not window_end:
        window_start, window_end = calc_window(cycle)

    db = SessionLocal()
    try:
        existing = ReportTaskRepo.find_existing(db, cycle, window_start, window_end)
        if existing:
            logger.info(f"[TASK] 幂等命中，复用任务 #{existing.id}（{existing.status}）")
            return {"task_id": existing.id, "reused": True, "status": existing.status}

        task = ReportTaskRepo.create(
            db, cycle=cycle, window_start=window_start, window_end=window_end,
            status="PENDING", trigger_type=trigger_type,
            trace_id=get_trace_id(),
        )
        logger.info(f"[TASK] 创建报告任务 #{task.id}: {cycle} {window_start} ~ {window_end}")
        return {"task_id": task.id, "reused": False, "status": task.status}
    finally:
        db.close()
