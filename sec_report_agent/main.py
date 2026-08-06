"""应用入口 — FastAPI 装配：全局异常拦截 / TraceID / CORS / 生命周期 / 路由注册"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import settings
from common.exception.exception import SecReportError
from common.logger.logger import LogManager
from api.response import ApiResponse, ApiCode
from infra.trace.trace import TraceMiddleware, set_trace_id, get_trace_id
from infra.db.session import init_db

logger = LogManager.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表 + 启动调度器；关闭时回收"""
    init_db()
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

# CORS（开发期全放开，前端 vite 默认 5173）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# ── 健康检查 ──
@app.get("/health")
async def health():
    return ApiResponse.ok(data={
        "app": settings.app_name,
        "env": settings.app_env,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "db": "sqlite" if settings.database_url.startswith("sqlite") else "mysql",
        "cache": settings.cache_backend,
    }, message="ok")


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
