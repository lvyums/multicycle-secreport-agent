"""通用参数校验器 — 非空/枚举/范围/时间窗口校验"""

from datetime import datetime
from typing import Any, Optional, Sequence

from common.exception.exception import BusinessError


def validate_required(value: Any, field_name: str):
    """非空校验（None/空串/空列表均拒绝）"""
    if value is None:
        raise BusinessError(f"参数缺失: {field_name}", code=400)
    if isinstance(value, str) and not value.strip():
        raise BusinessError(f"参数不能为空: {field_name}", code=400)
    if isinstance(value, (list, dict, tuple)) and len(value) == 0:
        raise BusinessError(f"参数不能为空: {field_name}", code=400)


def validate_enum(value: Any, allowed: Sequence, field_name: str):
    """枚举校验"""
    if value not in allowed:
        raise BusinessError(
            f"参数非法: {field_name} 必须为 {list(allowed)} 之一，实际: {value}", code=400
        )


def validate_range(value: Any, field_name: str, min_value: Optional[float] = None, max_value: Optional[float] = None):
    """数值范围校验"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BusinessError(f"参数类型错误: {field_name} 必须为数值", code=400)
    if min_value is not None and value < min_value:
        raise BusinessError(f"参数越界: {field_name} 不能小于 {min_value}", code=400)
    if max_value is not None and value > max_value:
        raise BusinessError(f"参数越界: {field_name} 不能大于 {max_value}", code=400)


def parse_datetime(value: str, field_name: str = "时间") -> datetime:
    """解析 ISO 时间字符串（兼容 2026-08-01 与 2026-08-01 00:00:00）"""
    if not value:
        raise BusinessError(f"参数缺失: {field_name}", code=400)
    text = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise BusinessError(f"时间格式非法: {value}，支持 YYYY-MM-DD / YYYY-MM-DD HH:MM[:SS]", code=400)


def validate_window(start: str, end: str, max_days: int = 370):
    """时间窗口校验：必填 + 顺序 + 跨度上限"""
    dt_start = parse_datetime(start, "startTime")
    dt_end = parse_datetime(end, "endTime")
    if dt_end <= dt_start:
        raise BusinessError("时间窗口非法: endTime 必须晚于 startTime", code=400)
    if (dt_end - dt_start).days > max_days:
        raise BusinessError(f"时间窗口跨度不能超过 {max_days} 天", code=400)
    return dt_start, dt_end
