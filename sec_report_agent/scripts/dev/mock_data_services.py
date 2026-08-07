"""开发联调验证服务 — ES 协议 + 告警平台 API 协议（V2.5 真实对接验证用）

用途：验证 EsAdapter / ApiAdapter 的真实 HTTP 对接代码（请求构造/认证/分页/解析）。
按真实协议响应（ES _search 结构、告警平台分页结构），数据在内存中按时间过滤。
生产环境适配器填真实集群/平台地址即可，无需本服务。

用法: python3 scripts/dev/mock_data_services.py
  POST /es/_search             → ES 检索响应(hits.hits[]._source + sort)
  GET  /es/_cluster/health     → ES 健康检查
  GET  /api/v1/alerts          → 告警平台分页接口(认证: X-API-Key: dev-key-123)
"""
import json
import re
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 模拟 ES 文档（@timestamp 近 24h 均匀分布）
ES_DOCS = []
base = datetime(2026, 8, 7, 0, 0, 0)
for i in range(40):
    ts = base + timedelta(minutes=30 * i)
    ES_DOCS.append({
        "@timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "severity": "HIGH" if i % 3 == 0 else ("MEDIUM" if i % 3 == 1 else "LOW"),
        "src_ip": f"203.0.113.{i % 20 + 1}",
        "host": f"web-{i % 5 + 1}",
        "event": {"type": "alert", "name": f"brute_force_{i}"},
    })

# 模拟告警平台数据（time 近 24h）
API_ALERTS = []
for i in range(30):
    ts = base + timedelta(minutes=45 * i)
    API_ALERTS.append({
        "time": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "severity": "HIGH" if i % 2 == 0 else "MEDIUM",
        "src_ip": f"198.51.100.{i % 15 + 1}",
        "asset": f"server-{i % 6 + 1}",
        "name": f"web_attack_{i}",
        "type": "web_attack",
    })


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        print(f"[DEV-SVC] GET {self.path}")
        if self.path == "/_cluster/health":
            return self._json(200, {"cluster_name": "dev-cluster", "status": "green"})
        if self.path.startswith("/api/v1/alerts"):
            from urllib.parse import urlparse, parse_qs
            if self.headers.get("X-API-Key") != "dev-key-123":
                return self._json(401, {"error": "invalid api key"})
            qs = parse_qs(urlparse(self.path).query)
            page = int(qs.get("page", ["1"])[0])
            size = int(qs.get("page_size", ["10"])[0])
            ws, we = qs.get("start_time", [""])[0], qs.get("end_time", [""])[0]
            items = [a for a in API_ALERTS if (not ws or a["time"] >= ws) and (not we or a["time"] <= we)]
            start = (page - 1) * size
            return self._json(200, {"data": items[start:start + size], "total": len(items)})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        body = self._read_body()
        print(f"[DEV-SVC] POST {self.path} ← {json.dumps(body, ensure_ascii=False)[:100]}")
        if self.path.endswith("/_search"):
            return self._es_search(body)
        return self._json(404, {"error": "not found"})

    def _es_search(self, body: dict):
        must = (body.get("query") or {}).get("bool", {}).get("must", [])
        gte = lte = None
        for m in must:
            rng = m.get("range") or {}
            for tf, cond in rng.items():
                gte = cond.get("gte", gte)
                lte = cond.get("lte", lte)

        def _norm(s):
            # 模拟 ES 日期解析: "2026-08-07 00:00:00" 与 ISO 等价
            return s.replace(" ", "T") if s and " " in s else s

        gte, lte = _norm(gte), _norm(lte)
        size = int(body.get("size", 10))
        search_after = body.get("search_after")
        hits = []
        for doc in ES_DOCS:
            ts = doc["@timestamp"]
            if gte and ts < gte:
                continue
            if lte and ts > lte:
                continue
            hits.append({"_index": "security-alerts-2026.08", "_id": f"doc_{ts}",
                         "_source": doc, "sort": [ts, f"doc_{ts}"]})
        # search_after 翻页: 只返回 sort 大于游标之后的
        if search_after:
            cursor = search_after[0]
            hits = [h for h in hits if h["sort"][0] > cursor]
        page = hits[:size]
        return self._json(200, {
            "took": 3, "timed_out": False,
            "hits": {"total": {"value": len(hits)}, "hits": page},
        })

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 19091), Handler)
    print("dev data services on http://127.0.0.1:19091")
    print("  ES:   GET /es/_cluster/health | POST /es/_search")
    print("  Alert API: GET /api/v1/alerts (X-API-Key: dev-key-123)")
    server.serve_forever()
