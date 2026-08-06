"""Syslog 适配器 — 解析 RFC3166 简化格式日志（mock 文件源）"""

import os
import re
from typing import Optional

from capability.adapter.adapter_base import DataSourceAdapter
from common.logger.logger import LogManager

logger = LogManager.get_logger()

# <PRI>Mmm dd HH:MM:SS host proc[pid]: msg
SYSLOG_RE = re.compile(
    r"^<(\d+)>(\w{3})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\S+)\s+(\w+)\[(\d+)\]:\s*(.*)$"
)

MONTH_MAP = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

# 消息关键词 → 风险初判
RISK_HINTS = [
    ("Failed password", "HIGH"),
    ("Malware", "HIGH"),
    ("Lateral", "HIGH"),
    ("WAF blocked", "MEDIUM"),
    ("Flood", "MEDIUM"),
    ("Phishing", "MEDIUM"),
    ("Policy violation", "LOW"),
]


class SyslogAdapter(DataSourceAdapter):
    """Syslog 日志源适配器（读取本地 mock 日志文件）"""

    type = "SYSLOG"

    def validate_config(self) -> list[str]:
        errors = []
        file_path = (self.config.config_json or {}).get("file_path", "")
        if not file_path:
            errors.append("缺少 file_path 配置")
        elif not os.path.exists(file_path):
            errors.append(f"日志文件不存在: {file_path}")
        return errors

    def fetch(self, window_start: str, window_end: str, task_id: int = 0) -> list[dict]:
        file_path = (self.config.config_json or {}).get("file_path", "")
        if not os.path.exists(file_path):
            logger.error(f"[SYSLOG] 文件不存在: {file_path}")
            return []
        events: list[dict] = []
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parsed = self.parse_line(line, window_start, window_end)
                if parsed:
                    events.append(parsed)
        logger.info(f"[SYSLOG] {self.name} 拉取 {len(events)} 条（窗口 {window_start}~{window_end}）")
        return events

    def parse_line(self, line: str, window_start: str, window_end: str) -> Optional[dict]:
        """解析单行 syslog → raw dict（窗口外丢弃）"""
        m = SYSLOG_RE.match(line)
        if not m:
            return None
        pri, month, day, hms, host, proc, pid, msg = m.groups()
        try:
            ts = f"2026-{MONTH_MAP[month]:02d}-{int(day):02d} {hms}"
        except (KeyError, ValueError):
            return None
        # 窗口过滤（字符串比较，ISO 格式可直接比较）
        if ts < window_start or ts > window_end:
            return None

        risk = "INFO"
        for kw, r in RISK_HINTS:
            if kw in msg:
                risk = r
                break

        src_ip = self._extract_ip(msg)
        return {
            "source_type": "SYSLOG",
            "source_name": self.name,
            "receive_time": ts,
            "raw_content": line,
            "status": "OK",
            "extra": {
                "event_type": proc,
                "risk_hint": risk,
                "src_ip": src_ip,
                "asset_ip": host if host.startswith("10.") else "",
                "device": host,
                "pid": pid,
                "priority": pri,
            },
        }

    @staticmethod
    def _extract_ip(text: str) -> str:
        ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
        return ips[0] if ips else ""
