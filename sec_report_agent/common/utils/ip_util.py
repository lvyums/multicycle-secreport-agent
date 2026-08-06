"""IP解析与归属地工具"""

import re
from typing import Optional

IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PRIVATE_IP_RANGES = [
    ("10.0.0.0", "10.255.255.255"),
    ("172.16.0.0", "172.31.255.255"),
    ("192.168.0.0", "192.168.255.255"),
]


def _ip_to_int(ip: str) -> int:
    parts = ip.split(".")
    return (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])


def parse_ip(text: str) -> list[str]:
    """从文本中提取所有 IP 地址"""
    return IP_PATTERN.findall(text)


def is_private_ip(ip: str) -> bool:
    """判断是否为私有 IP 地址"""
    try:
        ip_int = _ip_to_int(ip)
    except (ValueError, IndexError):
        return False
    for start, end in PRIVATE_IP_RANGES:
        if _ip_to_int(start) <= ip_int <= _ip_to_int(end):
            return True
    return False


def get_ip_location(ip: str) -> str:
    """IP 归属地查询（当前返回占位，后续对接 IP 库）"""
    if is_private_ip(ip):
        return "内网地址"
    return f"外部地址"