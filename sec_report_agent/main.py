"""应用入口 — FastAPI 装配：全局异常拦截 / TraceID / CORS / 生命周期 / 路由注册"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from config.settings import settings
from common.exception.exception import SecReportError
from common.logger.logger import LogManager
from api.response import ApiResponse, ApiCode
from infra.trace.trace import TraceMiddleware, set_trace_id, get_trace_id
from infra.db.session import init_db

logger = LogManager.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表 + 列迁移 + 任务恢复 + 种子用户 + 调度器；关闭时回收"""
    # 生产强校验（V2.2）：SECRET_KEY 与 CORS 白名单必须显式配置
    if settings.app_env == "production":
        if settings.secret_key == "sec-report-dev-secret-change-me":
            raise RuntimeError(
                "[APP] 生产环境必须设置 SECRET_KEY：export SECRET_KEY=$(openssl rand -hex 32)"
            )
        if (settings.cors_origins or "*").strip() == "*":
            raise RuntimeError("[APP] 生产环境必须显式配置 CORS_ORIGINS（逗号分隔白名单）")
    init_db()
    # 列迁移（V2.2：老库补 sys_user 新列）
    try:
        from infra.db.session import SessionLocal
        from infra.db.migrate import run_migrations
        _db = SessionLocal()
        try:
            applied = run_migrations(_db)
            if applied:
                logger.info(f"[APP] 列迁移完成: {', '.join(applied)}")
        finally:
            _db.close()
    except Exception as e:
        logger.warning(f"[APP] 列迁移失败（不影响主服务）: {e}")
    # 任务恢复（V2.2 B1）：启动时重置遗留 PENDING/RUNNING → FAILED
    if settings.recover_on_startup:
        try:
            from sqlalchemy import update as sa_update
            from model.entity.entities import ReportTask
            _db = SessionLocal()
            try:
                n = _db.execute(
                    sa_update(ReportTask)
                    .where(ReportTask.status.in_(["PENDING", "RUNNING"]))
                    .values(
                        status="FAILED",
                        error_msg="服务重启中断，请重跑",
                        finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                ).rowcount
                if n:
                    _db.commit()
                    logger.info(f"[APP] 任务恢复：{n} 个遗留任务已重置 FAILED")
            finally:
                _db.close()
        except Exception as e:
            logger.warning(f"[APP] 任务恢复失败（不影响主服务）: {e}")
    # 种子用户（V2.0 RBAC，幂等）
    try:
        from infra.db.session import SessionLocal
        from infra.db.repositories import UserRepo
        _db = SessionLocal()
        try:
            UserRepo.ensure_seed_users(_db)
            logger.info("[APP] 种子用户就绪（admin/analyst/viewer）")
        finally:
            _db.close()
    except Exception as e:
        logger.warning(f"[APP] 种子用户初始化失败: {e}")
    try:
        from infra.schedule.simple_scheduler import SimpleScheduler
        from app.scheduler import build_scheduler
        scheduler = build_scheduler()
        app.state.scheduler = scheduler
        if settings.schedule_enabled:
            scheduler.start()
            logger.info("[APP] 五周期调度器已启动")
    except Exception as e:
        logger.warning(f"[APP] 调度器启动失败（不影响主服务）: {e}")
    yield
    try:
        app.state.scheduler.shutdown()
    except Exception:
        pass
    from capability.judge.llm_factory import LLMFactory
    try:
        await LLMFactory.close_all()
    except Exception:
        pass


app = FastAPI(
    title="多周期网安报告智能体",
    description="MultiCycle SecReport Agent — 日/周/月/季/年五周期网络安全态势报告自动生成系统",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（V2.2：白名单配置化，settings.cors_origins 逗号分隔；生产强校验拒绝默认 *）
def _parse_cors_origins() -> list[str]:
    raw = (settings.cors_origins or "*").strip()
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TraceMiddleware)


# ── 全局异常拦截 ──
@app.exception_handler(SecReportError)
async def sec_report_error_handler(request: Request, exc: SecReportError):
    logger.warning(f"[EXC] {exc.code} {exc.message} path={request.url.path}")
    return JSONResponse(
        status_code=200,  # 业务错误统一 HTTP 200，由 code 区分
        content=ApiResponse.fail(message=exc.message, code=exc.code, data=exc.data),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error(f"[EXC] 未捕获异常 path={request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ApiResponse.fail(message=f"系统内部错误: {exc}", code=ApiCode.INTERNAL_ERROR),
    )


# ── 健康检查（V2.3 就绪探针：依赖明细，全挂才 503） ──
def _check_db() -> tuple[bool, str]:
    try:
        from infra.db.session import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            return True, "ok"
        finally:
            db.close()
    except Exception as e:
        return False, f"fail: {e}"


def _check_cache() -> tuple[bool, str]:
    try:
        from infra.cache.cache import get_cache
        c = get_cache()
        c.set("__health__", 1, ttl=5)
        return (c.get("__health__") is not None), "ok"
    except Exception as e:
        return False, f"fail: {e}"


def _check_vector() -> tuple[bool, str]:
    try:
        from config.settings import settings as _s
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        d = os.path.join(root, "vector_data")
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".health_probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True, "ok"
    except Exception as e:
        return False, f"fail: {e}"


@app.get("/health")
async def health():
    checks = {}
    db_ok, db_st = _check_db()
    cache_ok, cache_st = _check_cache()
    vector_ok, vector_st = _check_vector()
    checks["db"] = db_st
    checks["cache"] = cache_st
    checks["vector"] = vector_st
    overall = db_ok and cache_ok and vector_ok
    if overall:
        return ApiResponse.ok(data={
            "app": settings.app_name,
            "env": settings.app_env,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "checks": checks,
            "status": "ok",
        }, message="ok")
    # 就绪探针：任一核心依赖挂 → 503（容器编排/负载均衡摘流量）
    bad = [k for k, v in checks.items() if not v.startswith("ok")]
    return JSONResponse(
        status_code=503,
        content={
            "code": ApiCode.INTERNAL_ERROR, "message": f"依赖异常: {bad}",
            "data": {"status": "degraded", "checks": checks},
        },
    )


# ── 指标（V2.3 Prometheus 文本格式，零依赖） ──
@app.get("/metrics")
async def metrics_endpoint():
    from infra import metrics
    return Response(
        content=metrics.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# ── 路由注册（V1.0 阶段按模块挂载）──
def register_routers():
    try:
        from api.routers.report import router as report_router
        app.include_router(report_router, prefix="/api/report", tags=["报告"])
    except ImportError:
        pass
    try:
        from api.routers.schedule import router as schedule_router
        app.include_router(schedule_router, prefix="/api/schedule", tags=["调度"])
    except ImportError:
        pass
    try:
        from api.routers.version import router as version_router
        app.include_router(version_router, prefix="/api/version", tags=["版本"])
    except ImportError:
        pass
    try:
        from api.routers.publish import router as publish_router
        app.include_router(publish_router, prefix="/api/publish", tags=["推送"])
    except ImportError:
        pass
    try:
        from api.routers.datasource import router as datasource_router
        app.include_router(datasource_router, prefix="/api/datasource", tags=["数据源"])
    except ImportError:
        pass
    try:
        from api.routers.knowledge import router as kb_router
        app.include_router(kb_router, prefix="/api/kb", tags=["知识库"])
    except ImportError:
        pass
    try:
        from api.routers.config import router as config_router
        app.include_router(config_router, prefix="/api/config/report", tags=["报告选配"])
    except ImportError:
        pass
    try:
        from api.routers.auth import router as auth_router
        app.include_router(auth_router, prefix="/api/auth", tags=["认证"])
    except ImportError:
        pass


register_routers()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)
