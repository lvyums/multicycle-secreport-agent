"""DB 适配器 — 资产漏洞台账（mock CSV 文件源）"""

import csv
import os
from typing import Optional

from capability.adapter.adapter_base import DataSourceAdapter
from common.logger.logger import LogManager

logger = LogManager.get_logger()


class DbAdapter(DataSourceAdapter):
    """漏洞台账适配器（V1.0 读取本地 mock csv）"""

    type = "DB"

    def validate_config(self) -> list[str]:
        errors = []
        file_path = (self.config.config_json or {}).get("file_path", "")
        if not file_path:
            errors.append("缺少 file_path 配置")
        elif not os.path.exists(file_path):
            errors.append(f"台账文件不存在: {file_path}")
        return errors

    def fetch(self, window_start: str, window_end: str, task_id: int = 0) -> list[dict]:
        file_path = (self.config.config_json or {}).get("file_path", "")
        if not os.path.exists(file_path):
            logger.error(f"[DB] 文件不存在: {file_path}")
            return []
        events: list[dict] = []
        with open(file_path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                events.append({
                    "source_type": "DB",
                    "source_name": self.name,
                    "receive_time": row.get("discover_time") or "",
                    "raw_content": ",".join(f"{k}={v}" for k, v in row.items()),
                    "status": "OK",
                    "extra": {
                        "event_type": "vuln",
                        "risk_hint": str(row.get("risk_level") or "LOW").upper(),
                        "asset_ip": row.get("asset_ip") or "",
                        "asset_name": row.get("asset_name") or "",
                        "vuln_name": row.get("vuln_name") or "",
                        "cvss": float(row.get("cvss") or 0),
                        "vuln_status": row.get("status") or "",
                        "source_name": row.get("source_name") or "",
                    },
                })
        logger.info(f"[DB] {self.name} 拉取 {len(events)} 条漏洞台账")
        return events
