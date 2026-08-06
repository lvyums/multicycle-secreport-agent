"""统一接口响应封装 — ApiResponse 结构 {code, message, data, traceId, timestamp}"""

from typing import Any, Optional
import time

from infra.trace.trace import get_trace_id


class ApiCode:
    """统一状态码"""

    SUCCESS = 0
    PARAM_ERROR = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_ERROR = 500
    # 业务码段 1000+
    BUSINESS_ERROR = 1001
    DATA_SOURCE_ERROR = 2001
    SCHEDULE_ERROR = 3001
    LLM_ERROR = 4001
    TEMPLATE_ERROR = 5001
    STORAGE_ERROR = 6001


class ApiResponse:
    """统一响应结构"""

    @staticmethod
    def ok(data: Any = None, message: str = "success") -> dict:
        return {
            "code": ApiCode.SUCCESS,
            "message": message,
            "data": data if data is not None else {},
            "traceId": get_trace_id(),
            "timestamp": int(time.time() * 1000),
        }

    @staticmethod
    def fail(message: str, code: int = ApiCode.INTERNAL_ERROR, data: Any = None) -> dict:
        return {
            "code": code,
            "message": message,
            "data": data if data is not None else {},
            "traceId": get_trace_id(),
            "timestamp": int(time.time() * 1000),
        }

    @staticmethod
    def from_exception(code: int, message: str, data: Any = None) -> dict:
        return ApiResponse.fail(message=message, code=code, data=data)


def ok(data: Any = None, message: str = "success") -> dict:
    """快捷函数"""
    return ApiResponse.ok(data=data, message=message)


def fail(message: str, code: int = ApiCode.INTERNAL_ERROR, data: Any = None) -> dict:
    """快捷函数"""
    return ApiResponse.fail(message=message, code=code, data=data)
