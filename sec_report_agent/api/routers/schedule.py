"""调度 API — 任务列表 / 下次运行 / 立即触发 / 启停"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.response import ok, fail, ApiCode
from api.auth_deps import require_login, require_admin, require_analyst
from infra.db.session import get_db
from common.validator.validator import validate_enum
from model.enum.enums import ReportCycle

router = APIRouter()


def _get_scheduler(request: Request):
    return getattr(request.app.state, "scheduler", None)


@router.get("/list")
def schedule_list(request: Request, _=Depends(require_login)):
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
    jobs = []
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
def next_run(cycle: str, request: Request, _=Depends(require_login)):
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
def trigger(body: dict, request: Request, _=Depends(require_analyst)):
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
def toggle(body: dict, request: Request, _=Depends(require_admin)):
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


# ═══════════ 错过窗口检测 + 一键补跑（V2.8） ═══════════

_MISSED_LOOKBACK = 3  # 往前检测 3 个窗口


@router.get("/missed")
def schedule_missed(db=Depends(get_db), _=Depends(require_login)):
    """检测错过窗口：各周期应生成但无任务记录的窗口（凌晨维护/断电/cron 错过）"""
    from datetime import datetime as _dt
    from app.tasks.report_task import calc_window
    from infra.db.repositories import ReportTaskRepo
    from model.entity.entities import ReportTask

    missed = []
    for cycle in ReportCycle:
        # 从最近窗口往前推 N 个窗口
        windows = []
        ref = None
        for _ in range(_MISSED_LOOKBACK + 1):
            ws, we = calc_window(cycle.value, ref)
            windows.append((ws, we))
            ref = _dt.strptime(ws, "%Y-%m-%d %H:%M:%S")
        # windows[0]=最近窗口（可能进行中），检查 windows[1:]，窗口必须已结束
        now = _dt.now()
        for ws, we in windows[1:]:
            we_dt = _dt.strptime(we, "%Y-%m-%d %H:%M:%S")
            if we_dt > now:
                continue
            exists = db.query(ReportTask).filter(
                ReportTask.cycle == cycle.value,
                ReportTask.window_start == ws,
            ).first()
            if not exists:
                missed.append({
                    "cycle": cycle.value,
                    "cycleLabel": cycle.label,
                    "windowStart": ws, "windowEnd": we,
                    "reason": "该窗口无任何生成记录（可能因停机/断电/cron 错过）",
                })
    return ok({"items": missed, "total": len(missed)})


@router.post("/backfill")
def schedule_backfill(body: dict, _=Depends(require_analyst)):
    """一键补跑指定窗口（trigger_type=BACKFILL，rerun 绕过幂等）"""
    import asyncio
    from app.services.report_service import ReportService

    cycle = (body.get("cycle") or "").upper()
    validate_enum(cycle, [c.value for c in ReportCycle], "cycle")
    ws = body.get("windowStart") or ""
    we = body.get("windowEnd") or ""
    if not ws or not we:
        return fail("windowStart/windowEnd 必填（来自 /missed 检测结果）", ApiCode.PARAM_ERROR)
    try:
        result = asyncio.run(ReportService.generate(
            cycle, ws, we, trigger_type="BACKFILL", rerun=True,
        ))
    except Exception as e:
        return fail(f"补跑异常: {str(e)[:200]}", ApiCode.BUSINESS_ERROR)
    return ok(result, message=f"已触发 {ReportCycle(cycle).label} 补跑 {ws[:10]}~{we[:10]}")
