"""时间格式化与日志时间解析工具"""

import re
from datetime import datetime
from typing import Optional

# 常见日志时间格式
LOG_TIME_PATTERNS = [
    # syslog: "Mar 15 10:30:25" (无年份，需特殊处理)
    (r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})", "%b %d %H:%M:%S", True),
    # Apache: "10/Oct/2023:13:55:36 +0000"
    (r"(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}\s+\+\d{4})", "%d/%b/%Y:%H:%M:%S %z", False),
    # ISO 8601: "2023-10-10T13:55:36Z"
    (r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?)", "%Y-%m-%dT%H:%M:%S", False),
    # MySQL: "2023-10-10 13:55:36"
    (r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", "%Y-%m-%d %H:%M:%S", False),
]


def parse_log_time(text: str) -> Optional[str]:
    """从日志文本中解析时间戳，返回标准化 ISO 格式"""
    if not text:
        return None
    for pattern, fmt, needs_year in LOG_TIME_PATTERNS:
        match = re.search(pattern, text)
        if match:
            try:
                dt = datetime.strptime(match.group(1), fmt)
                if needs_year:
                    # syslog 格式没有年份，使用当前年份
                    dt = dt.replace(year=datetime.now().year)
                return dt.isoformat()
            except ValueError:
                continue
    # 无时间戳匹配时返回当前时间作为兜底
    return datetime.now().isoformat()


def format_timestamp(dt: Optional[datetime] = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳，默认返回当前时间的字符串"""
    if dt is None:
        dt = datetime.now()
    return dt.strftime(fmt)