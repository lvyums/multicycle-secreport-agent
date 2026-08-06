"""统一接口返回封装 — 使用新版 {code, msg, data, timestamp} 格式"""

from typing import Any, Optional
import time


class Result:
    """统一接口返回格式"""

    @staticmethod
    def ok(data: Any = None, msg: str = "success") -> dict:
        return {
            "code": 0,
            "msg": msg,
            "data": data if data is not None else {},
            "timestamp": int(time.time() * 1000),
        }

    @staticmethod
    def fail(msg: str, code: int = 400, data: Any = None) -> dict:
        return {
            "code": code,
            "msg": msg,
            "data": data if data is not None else {},
            "timestamp": int(time.time() * 1000),
        }

    @staticmethod
    def from_exception(code: int, msg: str) -> dict:
        return {
            "code": code,
            "msg": msg,
            "data": {},
            "timestamp": int(time.time() * 1000),
        }