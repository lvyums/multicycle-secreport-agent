"""API 告警平台适配器（V2.5 真实对接版）

对接厂商/自研安全运营平台的告警查询 REST API：
  - test_connection: GET {endpoint}（带认证）探测，2xx 视为可达
  - fetch: 按时间窗口循环 GET 分页拉取，按 time_field 过滤窗口内告警

双模式（向后兼容）：
  - 配置含 endpoint → 真实 HTTP 对接（V2.5 新配置）
  - 仅配置 file_path → 旧版本地 jsonl 文件读取（V1.0 mock 数据源，标记 deprecated）

配置字段（见 capability/adapter/meta.py TYPE_META["API"]）：
  endpoint / auth_type(bearer|apikey|basic|none) / token / username / password
  time_field / time_format / page_size / extra_params
"""

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

from capability.adapter.adapter_base import DataSourceAdapter
from common.logger.logger import LogManager

logger = LogManager.get_logger()


def _http_json(method: str, url: str, payload: Optional[dict] = None,
               headers: Optional[dict] = None, timeout: int = 20):
    """发 HTTP JSON 请求，返回 (http_status, json_obj | raw_text)；网络异常 status=0"""
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except Exception as e:
        return 0, f"网络异常: {e}"


class ApiAdapter(DataSourceAdapter):
    """告警平台 REST 适配器"""

    type = "API"

    def _cfg(self, key: str, default=""):
        return (self.config.config_json or {}).get(key, default)

    def _is_http_mode(self) -> bool:
        return bool((self.config.config_json or {}).get("endpoint"))

    # ── 认证头 ──
    def _auth_headers(self) -> dict:
        auth_type = self._cfg("auth_type", "bearer")
        token = self._cfg("token", "")
        if auth_type == "bearer" and token:
            return {"Authorization": f"Bearer {token}"}
        if auth_type == "apikey" and token:
            return {"X-API-Key": token}
        if auth_type == "basic":
            import base64
            user = self._cfg("username", "")
            pwd = self._cfg("password", "")
            b64 = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            return {"Authorization": f"Basic {b64}"}
        return {}

    # ── 配置校验 ──
    def validate_config(self) -> list[str]:
        cfg = self.config.config_json or {}
        if self._is_http_mode():
            errors = []
            if not cfg.get("endpoint"):
                errors.append("缺少 endpoint（接口地址）")
            auth_type = self._cfg("auth_type", "bearer")
            if auth_type == "basic" and not (self._cfg("username") and self._cfg("password")):
                errors.append("basic 认证缺少 username/password")
            return errors
        # 旧文件模式
        file_path = cfg.get("file_path", "")
        if not file_path:
            return ["缺少 endpoint 或 file_path 配置"]
        if not os.path.exists(file_path):
            return [f"告警文件不存在: {file_path}"]
        return []

    # ── 连通测试 ──
    def test_connection(self) -> tuple[bool, str]:
        if not self._is_http_mode():
            return super().test_connection()
        errors = self.validate_config()
        if errors:
            return False, "; ".join(errors)
        endpoint = self._cfg("endpoint")
        # 探测: 带认证 GET 首页 1 条（多数平台支持 page/page_size）
        sep = "&" if "?" in endpoint else "?"
        probe = f"{endpoint}{sep}page=1&page_size=1"
        status, body = _http_json("GET", probe, headers=self._auth_headers())
        if status == 0:
            return False, f"接口不可达: {body}"
        if status >= 400:
            return False, f"接口返回 HTTP {status}: {str(body)[:150]}"
        return True, f"接口可达 HTTP {status}（认证通过）"

    # ── 窗口拉取 ──
    def fetch(self, window_start: str, window_end: str, task_id: int = 0) -> list[dict]:
        if self._is_http_mode():
            return self._fetch_http(window_start, window_end)
        return self._fetch_file(window_start, window_end)

    # ── HTTP 模式 ──
    def _fetch_http(self, window_start: str, window_end: str) -> list[dict]:
        errors = self.validate_config()
        if errors:
            logger.error(f"[API] {self.name} 配置不完整: {'; '.join(errors)}")
            return []
        endpoint = self._cfg("endpoint")
        time_field = self._cfg("time_field", "time")
        page_size = int(self._cfg("page_size", "500") or 500)
        extra_params = self._cfg("extra_params", "")
        try:
            extra = json.loads(extra_params) if extra_params else {}
        except json.JSONDecodeError:
            extra = {}

        events: list[dict] = []
        page = 1
        max_pages = 200
        while page <= max_pages:
            params = {"page": page, "page_size": page_size,
                      "start_time": window_start, "end_time": window_end}
            params.update(extra)
            sep = "&" if "?" in endpoint else "?"
            url = f"{endpoint}{sep}{urllib.parse.urlencode(params)}"
            status, body = _http_json("GET", url, headers=self._auth_headers())
            if status == 0 or status >= 400:
                logger.error(f"[API] {self.name} 拉取失败 HTTP {status}: {str(body)[:150]}")
                break
            items = self._extract_items(body)
            if not items:
                break
            for item in items:
                parsed = self.parse_item(item, window_start, window_end, time_field)
                if parsed:
                    events.append(parsed)
            if len(items) < page_size:
                break
            page += 1
            time.sleep(0.05)  # 温和限速，避免打爆平台
        logger.info(f"[API] {self.name} 拉取 {len(events)} 条（窗口 {window_start}~{window_end}, {page} 页）")
        return events

    @staticmethod
    def _extract_items(body) -> list[dict]:
        """从平台响应中提取列表：兼容 data/items/records/list 包裹"""
        if isinstance(body, list):
            return body
        if not isinstance(body, dict):
            return []
        for key in ("data", "items", "records", "list", "result"):
            v = body.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for k2 in ("items", "records", "list", "rows"):
                    v2 = v.get(k2)
                    if isinstance(v2, list):
                        return v2
        return []

    def parse_item(self, item: dict, window_start: str, window_end: str,
                   time_field: str = "time") -> Optional[dict]:
        """解析单条告警，窗口外返回 None"""
        ts = str(item.get(time_field) or "")
        if not ts:
            return None
        # 兼容 ISO8601 与时间戳
        if ts.replace(".", "").isdigit():
            try:
                ts = time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.localtime(float(ts)))
            except (ValueError, OSError):
                return None
        if ts < window_start or ts > window_end:
            return None
        severity = str(item.get("severity") or item.get("level") or "INFO").upper()
        # 归一化: CRITICAL→HIGH；UNKNOWN/空→LOW（兼容旧文件模式）
        _SEV_MAP = {"CRITICAL": "HIGH", "UNKNOWN": "LOW", "": "LOW"}
        severity = _SEV_MAP.get(severity, severity)
        event_type = (item.get("event_type") or item.get("category")
                      or item.get("alert_name") or item.get("name")
                      or item.get("title") or "api_alert")
        alert_name = item.get("name") or item.get("title") or item.get("alert_name") or ""
        return {
            "source_type": "API",
            "source_name": self.name,
            "receive_time": ts,
            "raw_content": json.dumps(item, ensure_ascii=False),
            "status": "OK",
            "extra": {
                "event_type": event_type,
                "risk_hint": severity,
                "asset_ip": item.get("src_ip") or item.get("source_ip") or "",
                "asset_name": item.get("asset") or item.get("host") or "",
                "alert_name": alert_name,
                "alert_id": item.get("id") or item.get("alert_id") or "",
                "alert_type": item.get("type") or item.get("category") or "",
            },
        }

    # ── 旧文件模式（V1.0 兼容） ──
    def _fetch_file(self, window_start: str, window_end: str) -> list[dict]:
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
        logger.info(f"[API] {self.name} 拉取 {len(events)} 条（文件模式，窗口 {window_start}~{window_end}）")
        return events
