"""调度装配 — 五周期 Cron 注册（V1.0 占位：任务函数由 D2 阶段接入 report_service）

周期映射：
    DAILY      cron_daily     每天 01:00
    WEEKLY     cron_weekly    每周一 01:30
    MONTHLY    cron_monthly   每月 1 日 02:00
    QUARTERLY  cron_quarterly 每季首月 1 日 02:30
    YEARLY     cron_yearly    每年 1 月 1 日 03:00
"""

from config.settings import settings
from common.logger.logger import LogManager
from model.enum.enums import ReportCycle

logger = LogManager.get_logger()

# 周期 → (cron 配置键, cron 表达式)
CYCLE_CRON = {
    ReportCycle.DAILY.value: ("cron_daily", settings.cron_daily),
    ReportCycle.WEEKLY.value: ("cron_weekly", settings.cron_weekly),
    ReportCycle.MONTHLY.value: ("cron_monthly", settings.cron_monthly),
    ReportCycle.QUARTERLY.value: ("cron_quarterly", settings.cron_quarterly),
    ReportCycle.YEARLY.value: ("cron_yearly", settings.cron_yearly),
}


def _scheduled_generate(cycle: str):
    """定时触发入口：计算窗口并生成报告（D2 阶段接入 report_service）"""
    from app.tasks.report_task import run_report_task
    logger.info(f"[SCHED] 触发 {cycle} 周期报告生成")
    try:
        run_report_task(cycle=cycle, trigger_type="SCHEDULE")
    except Exception as e:
        logger.error(f"[SCHED] {cycle} 报告生成失败: {e}")


def build_scheduler():
    """构建并注册五周期任务的调度器实例"""
    from infra.schedule.simple_scheduler import SimpleScheduler

    scheduler = SimpleScheduler()
    for cycle, (_, cron_expr) in CYCLE_CRON.items():
        scheduler.add_cron_job(job_id=f"report_{cycle.lower()}", cron_expr=cron_expr,
                               func=_scheduled_generate, cycle=cycle)
    return scheduler
