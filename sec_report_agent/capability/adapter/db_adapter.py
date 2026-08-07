"""漏洞台账数据库适配器（V2.5 真实对接版）

对接 MySQL 等关系库中的漏洞/资产台账：
  - test_connection: 建立连接执行 SELECT 1（校验认证 + 库可达）
  - fetch: SELECT 目标表，按 time_field 窗口过滤

双模式（向后兼容）：
  - 配置含 db_url → 真实数据库对接（V2.5 新配置）
  - 仅配置 file_path → 旧版本地 csv 读取（V1.0 mock 数据源，标记 deprecated）

配置字段（见 capability/adapter/meta.py TYPE_META["DB"]）：
  db_url / table / time_field / time_format / extra_fields
"""

import csv
import os
from typing import Optional

from capability.adapter.adapter_base import DataSourceAdapter
from common.logger.logger import LogManager

logger = LogManager.get_logger()


class DbAdapter(DataSourceAdapter):
    """漏洞台账数据库适配器"""

    type = "DB"

    def _cfg(self, key: str, default=""):
        return (self.config.config_json or {}).get(key, default)

    def _is_db_mode(self) -> bool:
        return bool((self.config.config_json or {}).get("db_url"))

    # ── 配置校验 ──
    def validate_config(self) -> list[str]:
        cfg = self.config.config_json or {}
        if self._is_db_mode():
            errors = []
            if not cfg.get("db_url"):
                errors.append("缺少 db_url（数据库连接串）")
            if not cfg.get("table"):
                errors.append("缺少 table（表名）")
            return errors
        file_path = cfg.get("file_path", "")
        if not file_path:
            return ["缺少 db_url 或 file_path 配置"]
        if not os.path.exists(file_path):
            return [f"台账文件不存在: {file_path}"]
        return []

    # ── 连通测试 ──
    def test_connection(self) -> tuple[bool, str]:
        if not self._is_db_mode():
            return super().test_connection()
        errors = self.validate_config()
        if errors:
            return False, "; ".join(errors)
        try:
            engine = self._engine()
            with engine.connect() as conn:
                conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            engine.dispose()
            return True, "数据库连接成功（SELECT 1 通过）"
        except Exception as e:
            return False, f"数据库连接失败: {str(e)[:150]}"

    def _engine(self):
        from sqlalchemy import create_engine
        db_url = self._cfg("db_url")
        kwargs = {"pool_pre_ping": True}
        if db_url.startswith("mysql"):
            kwargs["connect_args"] = {"connect_timeout": 8}
        return create_engine(db_url, **kwargs)

    # ── 窗口拉取 ──
    def fetch(self, window_start: str, window_end: str, task_id: int = 0) -> list[dict]:
        if self._is_db_mode():
            return self._fetch_db(window_start, window_end)
        return self._fetch_file(window_start, window_end)

    # ── 数据库模式 ──
    def _fetch_db(self, window_start: str, window_end: str) -> list[dict]:
        from sqlalchemy import text

        errors = self.validate_config()
        if errors:
            logger.error(f"[DB] {self.name} 配置不完整: {'; '.join(errors)}")
            return []
        table = self._cfg("table")
        time_field = self._cfg("time_field", "discover_time")
        extra_fields = self._cfg("extra_fields", "")
        try:
            import json as _json
            field_map = _json.loads(extra_fields) if extra_fields else {}
        except Exception:
            field_map = {}

        try:
            engine = self._engine()
            sql = (f"SELECT * FROM `{table}` WHERE `{time_field}` >= :ws "
                   f"AND `{time_field}` <= :we")
            with engine.connect() as conn:
                rows = conn.execute(text(sql), {"ws": window_start, "we": window_end}).mappings().all()
            engine.dispose()
        except Exception as e:
            logger.error(f"[DB] {self.name} 查询失败: {e}")
            return []

        events: list[dict] = []
        for row in rows:
            r = dict(row)
            ts = str(r.get(time_field) or "")
            risk = str(r.get("risk_level") or r.get("severity") or "LOW").upper()
            extra = {
                "event_type": "vuln",
                "risk_hint": risk,
                "asset_ip": str(r.get("asset_ip") or ""),
                "asset_name": str(r.get("asset_name") or ""),
                "vuln_name": str(r.get("vuln_name") or ""),
                "cvss": float(r.get("cvss") or r.get("cvss_score") or 0),
                "vuln_status": str(r.get("status") or ""),
                "source_name": str(r.get("source_name") or ""),
            }
            # 自定义字段映射（台账列 → extra）
            for k, v in field_map.items():
                extra[k] = str(r.get(v) or "")
            events.append({
                "source_type": "DB",
                "source_name": self.name,
                "receive_time": ts,
                "raw_content": ",".join(f"{k}={v}" for k, v in r.items()),
                "status": "OK",
                "extra": extra,
            })
        logger.info(f"[DB] {self.name} 拉取 {len(events)} 条漏洞台账（窗口 {window_start}~{window_end}）")
        return events

    # ── 旧文件模式（V1.0 兼容） ──
    def _fetch_file(self, window_start: str, window_end: str) -> list[dict]:
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
        logger.info(f"[DB] {self.name} 拉取 {len(events)} 条漏洞台账（文件模式）")
        return events
