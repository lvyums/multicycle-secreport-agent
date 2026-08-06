"""TraceID 链路追踪 — contextvar 上下文 + 中间件注入

- 每个请求/任务生成唯一 trace_id（响应头 X-Trace-ID 返回）
- 日志、异常、任务链路统一携带 trace_id，便于全链路溯源
"""

import contextvars
import uuid
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from common.logger.logger import LogManager

logger = LogManager.get_logger()

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")


def generate_trace_id() -> str:
    """生成 32 位十六进制 trace_id"""
    return uuid.uuid4().hex


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """设置当前上下文 trace_id，未传则自动生成；返回最终值"""
    tid = trace_id or generate_trace_id()
    _trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    """获取当前上下文 trace_id（无则空串）"""
    return _trace_id_var.get()


class TraceMiddleware(BaseHTTPMiddleware):
    """请求链路中间件：透传/生成 TraceID 并注入响应头"""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Trace-ID", "")
        tid = set_trace_id(incoming or None)
        start = __import__("time").monotonic()
        try:
            response = await call_next(request)
        finally:
            duration_ms = int((__import__("time").monotonic() - start) * 1000)
            logger.info(f"[REQ] {request.method} {request.url.path} {duration_ms}ms trace={tid}")
        response.headers["X-Trace-ID"] = tid
        return response
