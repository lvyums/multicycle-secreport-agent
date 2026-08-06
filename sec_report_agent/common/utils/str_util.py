"""字符串清洗与匹配工具 — 日志预处理专用"""

import re
from typing import Optional

IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Syslog 头部模式: "Mar 15 10:30:25 server " 或 "<13>Mar 15 10:30:25 "
SYSLOG_HEADER = re.compile(
    r"^(<\d+>\s*)?"
    r"(?:\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+)"
    r"|^<\d+>\s*"
)


def clean_special_chars(text: str) -> str:
    """清洗特殊字符，保留基本文本内容"""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def clean_syslog_prefix(text: str) -> str:
    """清洗 Syslog 头部、无关前缀脏数据"""
    # 去除 Syslog 标准头部
    text = SYSLOG_HEADER.sub("", text)
    # 去除常见的无关前缀
    text = re.sub(r"^(INFO|WARN|ERROR|DEBUG|NOTICE)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[\+\.]\S+\s+\S+\s+", "", text)
    return text.strip()


def is_gibberish(text: str) -> bool:
    """判断是否为纯乱码/无意义字符"""
    if not text or not text.strip():
        return True
    stripped = text.strip()
    printable = sum(1 for c in stripped if c.isprintable() or c in "\n\r\t")
    if len(stripped) > 0 and printable / len(stripped) < 0.3:
        return True
    return False


def truncate(text: str, max_length: int = 1000, ellipsis: str = "...") -> str:
    """截断字符串到指定长度"""
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0] + ellipsis


def extract_ip_from_str(text: str) -> Optional[str]:
    """从字符串中提取第一个 IP 地址"""
    match = IP_PATTERN.search(text)
    return match.group(0) if match else None


def normalize_whitespace(text: str) -> str:
    """规范化空白字符（多个空格合并为一个）"""
    return re.sub(r"\s+", " ", text).strip()