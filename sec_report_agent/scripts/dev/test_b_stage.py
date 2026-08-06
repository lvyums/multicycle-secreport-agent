"""B 阶段全链路联调测试脚本（适配器→清洗→聚合）"""
import sys
sys.path.insert(0, ".")

from capability.adapter.mock_data_gen import ensure_mock_files
paths = ensure_mock_files()
print("mock files:", {k: v.split("/")[-1] for k, v in paths.items()})

from infra.db.session import SessionLocal, init_db
init_db()
db = SessionLocal()
from infra.db.repositories import DataSourceConfigRepo
cfgs = DataSourceConfigRepo.list_all(db)
ws, we = "2026-07-01 00:00:00", "2026-08-01 00:00:00"

from capability.adapter.factory import AdapterFactory
all_raw = []
vuln_raw = []
for c in cfgs:
    adapter = AdapterFactory.get(c)
    raw = adapter.fetch(ws, we)
    print(f"adapter {c.type}: {len(raw)} raw, errors={adapter.validate_config()}")
    if c.type == "DB":
        vuln_raw = raw
    else:
        all_raw.extend(raw)
db.close()

from capability.clean.handlers import build_default_chain
from capability.clean.data_chain import CleanContext
from model.struct.structs import StdEvent
chain = build_default_chain()
ctx = CleanContext(task_id=1, cycle="MONTHLY", window_start=ws, window_end=we)
events = []
for r in all_raw:
    ex = r.get("extra") or {}
    events.append(StdEvent(
        event_time=r["receive_time"], source_type=r["source_type"],
        event_type=ex.get("event_type") or "unknown",
        risk_level=ex.get("risk_hint") or "LOW",
        asset_ip=ex.get("asset_ip") or "", src_ip=ex.get("src_ip") or "",
        status=ex.get("alert_status") or "", device_source=ex.get("device") or "",
        raw_content=r["raw_content"], extra=ex,
    ))
cleaned = chain.process(events, ctx)
print(f"clean: input={ctx.stats['input']} kept={ctx.stats['kept']} dropped={ctx.stats['dropped']}")
print("drop:", {k: v for k, v in ctx.stats.items() if k.startswith("drop")})

from capability.metric.aggregator import MetricAggregator
agg = MetricAggregator("MONTHLY")
metric = agg.build(cleaned, [], ws, we)
print("alert total:", metric.alert["total"], "high:", metric.alert["high"],
      "close_rate:", metric.alert["close_rate"])
print("by_type:", list(metric.alert["by_type"].items())[:4])
print("top_src:", metric.top["top_src"][:2])
print("trend days:", len(metric.trend["by_day"]))

# 规则引擎联动
from capability.judge.rule_engine import build_default_engine
engine = build_default_engine()
flags = engine.evaluate_all(metric)
print("risk flags:", [(f.rule_name, f.level) for f in flags])
print("composite:", engine.composite_level(flags))
print("=== B STAGE PASS ===")
