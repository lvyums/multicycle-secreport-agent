"""C 阶段联调测试脚本（双路研判→渲染→版本快照，LLM 降级路径）"""
import asyncio
import sys
sys.path.insert(0, ".")

from capability.adapter.mock_data_gen import ensure_mock_files
ensure_mock_files()
from infra.db.session import SessionLocal, init_db
init_db()
from infra.db.repositories import DataSourceConfigRepo, ReportTaskRepo

from capability.adapter.factory import AdapterFactory
from capability.clean.handlers import build_default_chain
from capability.clean.data_chain import CleanContext
from model.struct.structs import StdEvent
from capability.metric.aggregator import MetricAggregator
from capability.judge.rule_engine import build_default_engine
from capability.rag.rag_facade import RAGFacade

ws, we = "2026-07-01 00:00:00", "2026-08-01 00:00:00"

# 1. 拉取+清洗+聚合（复用 B 链路）
db = SessionLocal()
cfgs = DataSourceConfigRepo.list_all(db)
all_raw, vuln_raw = [], []
for c in cfgs:
    adapter = AdapterFactory.get(c)
    raw = adapter.fetch(ws, we)
    if c.type == "DB":
        vuln_raw = raw
    else:
        all_raw.extend(raw)
db.close()

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
print(f"[1] clean: {len(cleaned)} kept / {len(events)} input")

agg = MetricAggregator("MONTHLY")
metric = agg.build(cleaned, [], ws, we)
print(f"[2] metric: total={metric.alert['total']} high={metric.alert['high']}")

# 2. 双路研判（规则 + LLM降级 + RAG）
engine = build_default_engine()
flags = engine.evaluate_all(metric)
print(f"[3] rules: {[(f.rule_name, f.level) for f in flags]} composite={engine.composite_level(flags)}")

facade = RAGFacade(enabled=True)
refs = facade.recall_for_metric(metric)
print(f"[4] rag refs: {len(refs)} (知识库可能为空)")

from capability.judge.llm_judge import LLMJudge
judge = LLMJudge()
result = asyncio.run(judge.judge(metric, flags, refs))
print(f"[5] judge: llm_ok={result.llm_ok} risk={result.risk_level} sections={list(result.sections.keys())}")
print(f"    overview: {result.sections.get('overview', '')[:80]}...")

# 3. 渲染（md + docx）
from capability.render.register import register_renderers
register_renderers()
from capability.render.render_base import RendererFactory
from datetime import datetime
from model.struct.structs import RenderData

data = RenderData(
    cycle="MONTHLY", cycle_label="月报", window_start=ws, window_end=we,
    generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    metric=metric.to_dict(), judge=result.to_dict(),
    extra={"title": "月报网络安全态势报告（2026-07-01 至 2026-08-01）"},
)
md_renderer = RendererFactory.get("md")
md_content = md_renderer.render(data)
print(f"[6] md render: {len(md_content)} chars, head: {md_content.splitlines()[0] if md_content else 'EMPTY'}")

import os, tempfile
tmp = tempfile.mkdtemp()
md_path = md_renderer.render_to_file(data, os.path.join(tmp, "monthly.md"))
docx_renderer = RendererFactory.get("docx")
docx_path = docx_renderer.render_to_file(data, os.path.join(tmp, "monthly.docx"))
print(f"[7] files: md={os.path.exists(md_path)} ({os.path.getsize(md_path)}B), docx={os.path.exists(docx_path)} ({os.path.getsize(docx_path)}B)")

# 4. 版本快照
from app.services.version_service import VersionService
from app.tasks.report_task import run_report_task
task = run_report_task("MONTHLY", window_start=ws, window_end=we)
print(f"[8] task: {task}")
version = VersionService.create_draft(
    task_id=task["task_id"], cycle="MONTHLY", window_start=ws, window_end=we,
    title=data.extra["title"], content_md=md_content, file_path=md_path,
)
print(f"[9] version: id={version['id']} v{version['versionNo']} status={version['status']}")
versions = VersionService.list_by_task(task["task_id"])
print(f"[10] versions by task: {len(versions)}")
content = VersionService.get_content(version["id"])
print(f"[11] content: {len(content['content'])} chars")
dl = VersionService.get_download(version["id"])
print(f"[12] download: {dl['path']} exists={dl['exists']}")
print("=== C STAGE PASS ===")
