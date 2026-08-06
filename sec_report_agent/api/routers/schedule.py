"""调度 API — 任务列表 / 下次运行 / 立即触发 / 启停"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.response import ok, fail
from common.validator.validator import validate_enum
from model.enum.enums import ReportCycle

router = APIRouter()


def _get_scheduler(request: Request):
    return getattr(request.app.state, "scheduler", None)


@router.get("/list")
def schedule_list(request: Request):
    """调度任务列表（含 cron 与下次触发时间）"""
    from config.settings import settings
    scheduler = _get_scheduler(request)
    cycle_cron = {
        ReportCycle.DAILY.value: settings.cron_daily,
        ReportCycle.WEEKLY.value: settings.cron_weekly,
        ReportCycle.MONTHLY.value: settings.cron_monthly,
        ReportCycle.QUARTERLY.value: settings.cron_quarterly,
        ReportCycle.YEARLY.value: settings.cron_yearly,
    }
    for cycle, cron in cycle_cron.items():
        next_run = None
        if scheduler:
            try:
                next_run = scheduler.get_next_run_time(f"report_{cycle.lower()}")
            except Exception:
                next_run = None
        jobs.append({
            "cycle": cycle, "cycleLabel": ReportCycle(cycle).label,
            "cron": cron, "nextRun": next_run,
            "desc": f"每{cron}触发{ReportCycle(cycle).label}生成",
        })
    return ok({"jobs": jobs, "enabled": settings.schedule_enabled})


@router.get("/next-run")
def next_run(cycle: str, request: Request):
    """指定周期下次触发时间"""
    validate_enum(cycle.upper(), [c.value for c in ReportCycle], "cycle")
    scheduler = _get_scheduler(request)
    next_run = None
    if scheduler:
        try:
            next_run = scheduler.get_next_run_time(f"report_{cycle.lower()}")
        except Exception:
            next_run = None
    return ok({"cycle": cycle.upper(), "nextRun": next_run})


@router.post("/trigger")
def trigger(body: dict, request: Request):
    """立即触发指定周期报告生成"""
    import asyncio
    from app.services.report_service import ReportService
    from app.tasks.report_task import calc_window

    cycle = (body.get("cycle") or "").upper()
    validate_enum(cycle, [c.value for c in ReportCycle], "cycle")
    ws, we = calc_window(cycle)
    result = asyncio.run(ReportService.generate(cycle, ws, we, trigger_type="SCHEDULE"))
    return ok(result, message=f"已触发 {ReportCycle(cycle).label} 生成")


@router.post("/toggle")
def toggle(body: dict, request: Request):
    """启停调度（配置项 schedule_enabled）"""
    from config.settings import settings
    enabled = bool(body.get("enabled", True))
    settings.schedule_enabled = enabled
    scheduler = _get_scheduler(request)
    if scheduler:
        if enabled:
            scheduler.start()
        else:
            scheduler.shutdown()
    return ok({"enabled": enabled}, message="调度已启用" if enabled else "调度已停用")
