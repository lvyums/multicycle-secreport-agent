"""调度装配 — 五周期 Cron 注册 + 下次运行时间查询

周期映射（settings 中 cron_* 可配）：
    DAILY      report_daily      每天 01:00
    WEEKLY     report_weekly     每周一 01:30
    MONTHLY    report_monthly    每月 1 日 02:00
    QUARTERLY  report_quarterly  每季度首日 02:30
    YEARLY     report_yearly     每年 1 月 1 日 03:00
"""

from config.settings import settings
from common.logger.logger import LogManager
from model.enum.enums import ReportCycle

logger = LogManager.get_logger()

JOB_CRON_MAP = {
    ReportCycle.DAILY.value: settings.cron_daily,
    ReportCycle.WEEKLY.value: settings.cron_weekly,
    ReportCycle.MONTHLY.value: settings.cron_monthly,
    ReportCycle.QUARTERLY.value: settings.cron_quarterly,
    ReportCycle.YEARLY.value: settings.cron_yearly,
}


def _job_func(cycle: str):
    """任务执行函数（同步包装，内部 asyncio.run）"""
    def _run():
        from app.tasks.report_task import run_report_task
        try:
            result = run_report_task(cycle, trigger_type="SCHEDULE")
            logger.info(f"[SCHED] {cycle} 自动生成完成: {result}")
        except Exception as e:
            logger.error(f"[SCHED] {cycle} 自动生成异常: {e}", exc_info=True)
    return _run


def build_scheduler():
    """构建并注册五周期调度任务"""
    from infra.schedule.simple_scheduler import SimpleScheduler

    scheduler = SimpleScheduler()
    for cycle, cron in JOB_CRON_MAP.items():
        if not cron:
            logger.warning(f"[SCHED] {cycle} 未配置 cron，跳过注册")
            continue
        scheduler.add_cron_job(f"report_{cycle.lower()}", cron, _job_func(cycle))
        logger.info(f"[SCHED] 已注册 {cycle}: cron={cron}")
    return scheduler
