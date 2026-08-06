"""威胁情报源适配器 — 解析外部情报 IOC（mock jsonl 文件源，V1.2）"""

import json
import os
from typing import Optional

from capability.adapter.adapter_base import DataSourceAdapter
from common.logger.logger import LogManager

logger = LogManager.get_logger()

CONFIDENCE_RISK = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}


class IntelAdapter(DataSourceAdapter):
    """外部威胁情报适配器（IOC 列表）"""

    type = "INTEL"

    def validate_config(self) -> list[str]:
        errors = []
        file_path = (self.config.config_json or {}).get("file_path", "")
        if not file_path:
            errors.append("缺少 file_path 配置")
        elif not os.path.exists(file_path):
            errors.append(f"情报文件不存在: {file_path}")
        return errors

    def fetch(self, window_start: str, window_end: str, task_id: int = 0) -> list[dict]:
        file_path = (self.config.config_json or {}).get("file_path", "")
        if not os.path.exists(file_path):
            logger.error(f"[INTEL] 文件不存在: {file_path}")
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
        logger.info(f"[INTEL] {self.name} 拉取 {len(events)} 条（窗口 {window_start}~{window_end}）")
        return events

    def parse_item(self, item: dict, window_start: str, window_end: str) -> Optional[dict]:
        ts = str(item.get("first_seen") or "")
        if not ts or ts < window_start or ts > window_end:
            return None
        confidence = str(item.get("confidence") or "low").lower()
        risk = CONFIDENCE_RISK.get(confidence, "LOW")
        return {
            "source_type": "INTEL",
            "source_name": self.name,
            "receive_time": ts,
            "raw_content": json.dumps(item, ensure_ascii=False),
            "status": "OK",
            "extra": {
                "event_type": "ioc_intel",
                "risk_hint": risk,
                "src_ip": item.get("ioc_value", "") if item.get("ioc_type") == "ip" else "",
                "device": "intel-feed",
                "ioc_type": str(item.get("ioc_type") or ""),
                "ioc_value": str(item.get("ioc_value") or ""),
                "confidence": confidence,
                "source": str(item.get("source") or ""),
                "tags": item.get("tags") or [],
            },
        }
