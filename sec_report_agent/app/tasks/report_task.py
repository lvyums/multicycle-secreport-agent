"""报告任务 — 周期窗口计算 + 同步执行入口（调度器/脚本调用）

run_report_task 委托 app.services.report_service（完整 pipeline）
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
                    window_start: str | None = None, window_end: str | None = None,
                    rerun: bool = False) -> dict:
    """同步入口：委托 ReportService 执行完整 pipeline"""
    from app.services.report_service import run_report_task as _run
    return _run(cycle, trigger_type=trigger_type,
                window_start=window_start, window_end=window_end, rerun=rerun)
