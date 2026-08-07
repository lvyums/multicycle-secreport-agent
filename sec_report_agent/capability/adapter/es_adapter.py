"""Elasticsearch 日志检索适配器（V2.5 真实对接）

对接 ES 集群 REST API 检索安全日志/告警：
  - test_connection: GET {es_url}/_cluster/health（校验认证 + 集群可达）
  - fetch: POST {es_url}/{index}/_search，bool 查询 = 时间窗口 range + 附加 DSL，
    按时间排序 + search_after 翻页，直到取完窗口内全部文档

配置字段（见 capability/adapter/meta.py TYPE_META["ES"]）：
  es_url / auth_type(basic|apikey|none) / username / password / api_key
  index_pattern / time_field / query_dsl / size

零新增依赖（urllib）。认证失败/集群不可达 → test_connection 返回明确失败原因。
"""

import json
import urllib.parse
import urllib.request
from typing import Optional

from capability.adapter.adapter_base import DataSourceAdapter
from common.logger.logger import LogManager

logger = LogManager.get_logger()


def _http_json(method: str, url: str, payload: Optional[dict] = None,
               headers: Optional[dict] = None, timeout: int = 15):
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


class EsAdapter(DataSourceAdapter):
    """Elasticsearch 日志检索适配器"""

    type = "ES"

    # ── 配置读取 ──
    def _cfg(self, key: str, default=""):
        return (self.config.config_json or {}).get(key, default)

    def _auth_headers(self) -> dict:
        auth_type = self._cfg("auth_type", "none")
        if auth_type == "basic":
            import base64
            user = self._cfg("username", "")
            pwd = self._cfg("password", "")
            token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            return {"Authorization": f"Basic {token}"}
        if auth_type == "apikey":
            return {"Authorization": f"ApiKey {self._cfg('api_key', '')}"}
        return {}

    def _base_url(self) -> str:
        return (self._cfg("es_url") or "").rstrip("/")

    # ── 配置校验 ──
    def validate_config(self) -> list[str]:
        errors = []
        if not self._base_url():
            errors.append("缺少 es_url（集群地址）")
        if not self._cfg("index_pattern"):
            errors.append("缺少 index_pattern（索引模式）")
        auth_type = self._cfg("auth_type", "none")
        if auth_type == "basic" and not (self._cfg("username") and self._cfg("password")):
            errors.append("basic 认证缺少 username/password")
        if auth_type == "apikey" and not self._cfg("api_key"):
            errors.append("apikey 认证缺少 api_key")
        return errors

    # ── 连通测试 ──
    def test_connection(self) -> tuple[bool, str]:
        errors = self.validate_config()
        if errors:
            return False, "; ".join(errors)
        status, body = _http_json("GET", f"{self._base_url()}/_cluster/health",
                                  headers=self._auth_headers())
        if status == 0:
            return False, f"ES 集群不可达: {body}"
        if status >= 400:
            return False, f"ES 认证/权限失败 HTTP {status}: {str(body)[:150]}"
        cluster = body.get("cluster_name") if isinstance(body, dict) else ""
        return True, f"ES 集群可达: {cluster} (HTTP {status})"

    # ── 窗口拉取 ──
    def fetch(self, window_start: str, window_end: str, task_id: int = 0) -> list[dict]:
        errors = self.validate_config()
        if errors:
            logger.error(f"[ES] {self.name} 配置不完整: {'; '.join(errors)}")
            return []
        index = self._cfg("index_pattern")
        time_field = self._cfg("time_field", "@timestamp")
        size = int(self._cfg("size", "500") or 500)
        url = f"{self._base_url()}/{urllib.parse.quote(index, safe='*,-')}/_search"

        # bool 查询: 时间窗口 range + 附加 DSL
        must: list[dict] = [{
            "range": {time_field: {"gte": window_start, "lte": window_end}},
        }]
        extra_dsl = self._cfg("query_dsl", "")
        if extra_dsl:
            try:
                extra = json.loads(extra_dsl)
                if isinstance(extra, dict):
                    must.append(extra)
            except json.JSONDecodeError:
                logger.warning(f"[ES] {self.name} query_dsl 非合法 JSON，忽略: {extra_dsl[:80]}")

        events: list[dict] = []
        search_after: Optional[list] = None
        pages = 0
        max_pages = 200
        while pages < max_pages:
            pages += 1
            query: dict = {
                "query": {"bool": {"must": must}},
                "sort": [{time_field: "asc"}, {"_id": "asc"}],
                "size": size,
                "_source": True,
            }
            if search_after:
                query["search_after"] = search_after
            status, body = _http_json("POST", url, payload=query,
                                      headers=self._auth_headers())
            if status == 0 or status >= 400:
                logger.error(f"[ES] {self.name} 检索失败 HTTP {status}: {str(body)[:150]}")
                break
            hits = (body.get("hits") or {}).get("hits") or []
            for hit in hits:
                src = hit.get("_source") or {}
                ts = str(src.get(time_field) or "")
                events.append({
                    "source_type": "ES",
                    "source_name": self.name,
                    "receive_time": ts,
                    "raw_content": json.dumps(src, ensure_ascii=False),
                    "status": "OK",
                    "extra": {
                        "event_type": "es_log",
                        "risk_hint": str(src.get("severity") or src.get("level") or "INFO").upper(),
                        "asset_ip": src.get("src_ip") or src.get("client_ip") or "",
                        "asset_name": src.get("host") or "",
                        "index": index,
                        "doc_id": hit.get("_id") or "",
                    },
                })
            if len(hits) < size:
                break
            search_after = hits[-1].get("sort")
            if not search_after:
                break
        logger.info(f"[ES] {self.name} 拉取 {len(events)} 条（窗口 {window_start}~{window_end}, {pages} 页）")
        return events
