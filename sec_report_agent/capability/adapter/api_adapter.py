"""API 适配器 — 解析告警平台 JSON（mock jsonl 文件源）"""

import json
import os
from typing import Optional

from capability.adapter.adapter_base import DataSourceAdapter
from common.logger.logger import LogManager

logger = LogManager.get_logger()

SEVERITY_MAP = {"CRITICAL": "HIGH", "HIGH": "HIGH", "MEDIUM": "MEDIUM",
                "LOW": "LOW", "INFO": "INFO"}


class ApiAdapter(DataSourceAdapter):
    """告警平台 REST 适配器（V1.0 读取本地 mock jsonl）"""

    type = "API"

    def validate_config(self) -> list[str]:
        errors = []
        file_path = (self.config.config_json or {}).get("file_path", "")
        if not file_path:
            errors.append("缺少 file_path 配置")
        elif not os.path.exists(file_path):
            errors.append(f"告警文件不存在: {file_path}")
        return errors

    def fetch(self, window_start: str, window_end: str, task_id: int = 0) -> list[dict]:
        file_path = (self.config.config_json or {}).get("file_path", "")
        if not os.path.exists(file_path):
            logger.error(f"[API] 文件不存在: {file_path}")
            return []
        events: list[dict] = []
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                parsed = self.parse_item(item, window_start, window_end)
                if parsed:
                    events.append(parsed)
        logger.info(f"[API] {self.name} 拉取 {len(events)} 条（窗口 {window_start}~{window_end}）")
        return events

    def parse_item(self, item: dict, window_start: str, window_end: str) -> Optional[dict]:
        ts = str(item.get("time") or "")
        if not ts or ts < window_start or ts > window_end:
            return None
        severity = str(item.get("severity") or "INFO").upper()
        return {
            "source_type": "API",
            "source_name": self.name,
            "receive_time": ts,
            "raw_content": json.dumps(item, ensure_ascii=False),
            "status": "OK",
            "extra": {
                "event_type": item.get("event_type") or item.get("alert_name") or "unknown",
                "risk_hint": SEVERITY_MAP.get(severity, "LOW"),
                "src_ip": item.get("src_ip") or "",
                "asset_ip": item.get("dst_ip") or "",
                "device": item.get("device") or "",
                "alert_id": item.get("id") or "",
                "rule_id": item.get("rule_id") or "",
                "alert_status": item.get("status") or "",
            },
        }
