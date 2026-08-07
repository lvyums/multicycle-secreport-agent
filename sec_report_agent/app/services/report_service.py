"""报告生成编排服务 — 全链路 pipeline（D2 核心）

流程：任务状态机 → 数据源拉取 → RawEvent 落地 → 清洗入库 → 指标聚合 →
      规则引擎+LLM双路研判 → 模板渲染(md+docx) → 版本快照 → 状态收尾

状态机：PENDING → RUNNING → SUCCESS / EMPTY / PARTIAL / FAILED
"""

import asyncio
import time
from datetime import datetime
from typing import Optional

from config.settings import settings
from common.logger.logger import LogManager
from common.exception.exception import DataSourceError
from model.enum.enums import TaskStatus, ReportStatus, TriggerType
from model.struct.structs import StdEvent, RenderData
from infra.trace.trace import get_trace_id

logger = LogManager.get_logger()


class ReportService:
    """报告生成服务"""

    # ── 对外入口 ──

    @classmethod
    async def generate(cls, cycle: str, window_start: str, window_end: str,
                       trigger_type: str = TriggerType.MANUAL.value,
                       rerun: bool = False) -> dict:
        """生成报告（异步编排全链路）"""
        from infra.db.session import SessionLocal
        from infra.db.repositories import ReportTaskRepo, AuditLogRepo

        db = SessionLocal()
        try:
            existing = None
            if not rerun:
                existing = ReportTaskRepo.find_existing(db, cycle, window_start, window_end)
            if existing:
                logger.info(f"[PIPE] 幂等命中任务 #{existing.id}（{existing.status}），直接返回")
                return {"task_id": existing.id, "reused": True, "status": existing.status}

            task = ReportTaskRepo.create(
                db, cycle=cycle, window_start=window_start, window_end=window_end,
                status=TaskStatus.RUNNING.value, trigger_type=trigger_type,
                trace_id=get_trace_id(), started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            task_id = task.id
            AuditLogRepo.add(db, operator="system", action="report_generate",
                             target_type="task", target_id=task_id,
                             detail=f"{cycle} {window_start}~{window_end} 触发={trigger_type}",
                             trace_id=get_trace_id())
            db.commit()
            logger.info(f"[PIPE] 任务 #{task_id} 开始执行: {cycle} {window_start}~{window_end}")
        finally:
            db.close()

        try:
            result = await cls._run_pipeline(task_id, cycle, window_start, window_end)
        except Exception as e:
            logger.error(f"[PIPE] 任务 #{task_id} 全链路异常: {e}", exc_info=True)
            result = {"status": TaskStatus.FAILED.value, "error": str(e)[:400]}
            cls._finish_task(task_id, TaskStatus.FAILED.value, error=str(e)[:400])
        return {"task_id": task_id, "reused": False, **result}

    @classmethod
    async def submit(cls, cycle: str, window_start: str, window_end: str,
                     trigger_type: str = TriggerType.MANUAL.value,
                     rerun: bool = False) -> dict:
        """异步提交（V2.0 R 性能）：创建 PENDING 任务立即返回，不阻塞请求"""
        from infra.db.session import SessionLocal
        from infra.db.repositories import ReportTaskRepo, AuditLogRepo

        db = SessionLocal()
        try:
            existing = None
            if not rerun:
                existing = ReportTaskRepo.find_existing(db, cycle, window_start, window_end)
            if existing:
                return {"task_id": existing.id, "reused": True, "status": existing.status}
            task = ReportTaskRepo.create(
                db, cycle=cycle, window_start=window_start, window_end=window_end,
                status=TaskStatus.PENDING.value, trigger_type=trigger_type,
                trace_id=get_trace_id(),
            )
            db.commit()
            AuditLogRepo.add(db, operator="system", action="report_submit",
                             target_type="task", target_id=task.id,
                             detail=f"{cycle} {window_start}~{window_end} 触发={trigger_type}",
                             trace_id=get_trace_id())
            logger.info(f"[PIPE] 任务 #{task.id} 已提交（PENDING）: {cycle}")
            return {"task_id": task.id, "reused": False, "status": TaskStatus.PENDING.value}
        finally:
            db.close()

    @classmethod
    async def run_background(cls, task_id: int, cycle: str, ws: str, we: str) -> dict:
        """后台执行 pipeline（V2.0 R 性能）：PENDING → RUNNING → 终态"""
        from infra.db.session import SessionLocal
        from infra.db.repositories import ReportTaskRepo

        db = SessionLocal()
        try:
            task = ReportTaskRepo.get(db, task_id)
            if task and task.status == TaskStatus.PENDING.value:
                task.status = TaskStatus.RUNNING.value
                task.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.commit()
        finally:
            db.close()

        try:
            result = await cls._run_pipeline(task_id, cycle, ws, we)
        except Exception as e:
            logger.error(f"[PIPE] 后台任务 #{task_id} 异常: {e}", exc_info=True)
            cls._finish_task(task_id, TaskStatus.FAILED.value, error=str(e)[:400])
            result = {"status": TaskStatus.FAILED.value, "error": str(e)[:400]}
        return {"task_id": task_id, **result}

    # ── 核心 pipeline ──

    @classmethod
    async def _run_pipeline(cls, task_id: int, cycle: str, ws: str, we: str) -> dict:
        start = time.monotonic()

        # 1. 数据源拉取（并行，单源失败不阻塞整体）
        raw_all, vuln_raw, stats = await cls._fetch_all(task_id, cycle, ws, we)
        partial = any(s.get("ok") is False for s in stats.values())

        # 2. RawEvent 落地 + 清洗入库
        cleaned, drop_stats = await cls._clean_and_store(task_id, cycle, ws, we, raw_all, vuln_raw)

        # 3. 指标聚合（缓存代理）
        metric = await cls._aggregate(cycle, ws, we, cleaned)

        # 4. 双路研判（规则引擎 + RAG + LLM）
        judge = await cls._judge(metric, cycle, ws, we)

        # 5. 渲染 + 版本快照
        version = await cls._render_and_snapshot(task_id, cycle, ws, we, metric, judge, cleaned)

        # 6. 状态收尾
        empty = metric.alert.get("total", 0) == 0 and metric.vuln.get("total", 0) == 0
        status = TaskStatus.EMPTY.value if empty else (TaskStatus.PARTIAL.value if partial else TaskStatus.SUCCESS.value)
        duration_ms = int((time.monotonic() - start) * 1000)
        cls._finish_task(task_id, status, duration_ms=duration_ms,
                         data_source_stats=stats, version_id=version.get("id", 0))

        # 7. 自动推送（报告选配 auto_generate，V1.3）
        if status == TaskStatus.SUCCESS.value:
            cls._auto_push_if_enabled(version.get("id", 0))

        logger.info(f"[PIPE] 任务 #{task_id} 完成: {status} 耗时{duration_ms}ms")
        return {"status": status, "version_id": version.get("id", 0),
                "event_count": metric.alert.get("total", 0), "partial": partial}

    # ── 环节实现 ──

    @classmethod
    async def _fetch_all(cls, task_id: int, cycle: str, ws: str, we: str) -> tuple[list, list, dict]:
        """拉取所有启用数据源（异步并行；HISTORY 注入当前周期用于环比）"""
        from infra.db.session import SessionLocal
        from infra.db.repositories import DataSourceConfigRepo
        from capability.adapter.factory import AdapterFactory

        db = SessionLocal()
        try:
            cfgs = DataSourceConfigRepo.get_enabled(db)
        finally:
            db.close()

        stats: dict = {}
        raw_all: list = []
        vuln_raw: list = []

        async def fetch_one(cfg):
            # V2.0 S 容错：失败重试 2 次（指数退避 0.3s/0.9s），单源失败不阻塞整体
            for attempt in range(3):
                try:
                    adapter = AdapterFactory.get(cfg)
                    if cfg.type == "HISTORY":
                        adapter.current_cycle = cycle  # 运行时注入当前周期（环比匹配同周期快照）
                    raw = adapter.fetch(ws, we)
                    stats[cfg.name] = {"ok": True, "count": len(raw), "type": cfg.type}
                    return cfg.type, raw
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(0.3 * (3 ** attempt))
                        continue
                    logger.error(f"[PIPE] 数据源 {cfg.name} 拉取失败（已重试2次）: {e}")
                    stats[cfg.name] = {"ok": False, "count": 0, "type": cfg.type, "error": str(e)[:200]}
                    return cfg.type, []

        results = await asyncio.gather(*[fetch_one(c) for c in cfgs])
        for stype, raw in results:
            if stype == "DB":
                vuln_raw.extend(raw)
            else:
                raw_all.extend(raw)
        return raw_all, vuln_raw, stats

    @classmethod
    async def _clean_and_store(cls, task_id: int, cycle: str, ws: str, we: str,
                               raw_all: list, vuln_raw: list) -> tuple[list, dict]:
        """RawEvent 落地 → 清洗 → StdEvent 入库（重跑先清旧数据）"""
        from infra.db.session import SessionLocal
        from infra.db.repositories import RawEventRepo, StdEventRepo
        from capability.clean.handlers import build_default_chain
        from capability.clean.data_chain import CleanContext

        db = SessionLocal()
        try:
            # RawEvent 落地
            raw_events = [{
                "source_type": r.get("source_type", ""), "source_name": r.get("source_name", ""),
                "receive_time": r.get("receive_time", ""), "raw_content": r.get("raw_content", ""),
                "status": r.get("status", "OK"), "task_id": task_id,
            } for r in raw_all]
            RawEventRepo.add_many(db, raw_events)

            # 重跑清理旧 StdEvent（幂等）
            StdEventRepo.delete_by_task(db, task_id)

            # 清洗
            chain = build_default_chain()
            ctx = CleanContext(task_id=task_id, cycle=cycle, window_start=ws, window_end=we)
            events = []
            for r in raw_all:
                ex = r.get("extra") or {}
                events.append(StdEvent(
                    event_time=r.get("receive_time", ""), source_type=r.get("source_type", ""),
                    event_type=ex.get("event_type") or "unknown",
                    risk_level=ex.get("risk_hint") or "LOW",
                    asset_ip=ex.get("asset_ip") or "", src_ip=ex.get("src_ip") or "",
                    status=ex.get("alert_status") or "", device_source=ex.get("device") or "",
                    raw_content=r.get("raw_content", ""), extra=ex,
                ))
            cleaned = chain.process(events, ctx)

            # StdEvent 入库
            std_rows = [{
                "event_time": e.event_time, "source_type": e.source_type,
                "event_type": e.event_type, "risk_level": e.risk_level,
                "asset_ip": e.asset_ip, "src_ip": e.src_ip, "status": e.status,
                "device_source": e.device_source, "raw_content": e.raw_content,
                "dedup_key": e.dedup_key, "extra": e.extra, "task_id": task_id,
            } for e in cleaned]
            StdEventRepo.add_many(db, std_rows)
            logger.info(f"[PIPE] 任务 #{task_id} 清洗入库: {len(cleaned)}/{len(events)}")
            return cleaned, ctx.stats
        finally:
            db.close()

    @classmethod
    async def _aggregate(cls, cycle: str, ws: str, we: str, cleaned: list):
        """指标聚合（模板方法 + 缓存代理；重跑先失效缓存防脏数据）

        从清洗结果提取 history_metric 事件（历史报告源），计算环比挂到 trend.compare
        """
        from capability.metric.aggregator import MetricAggregator
        from capability.metric.metric_base import CachedMetricProxy

        # 分离历史环比事件（不参与告警统计）
        history_events = [e for e in cleaned if getattr(e, "event_type", "") == "history_metric"]
        real_events = [e for e in cleaned if getattr(e, "event_type", "") != "history_metric"]

        aggregator = CachedMetricProxy(MetricAggregator(cycle), ttl=600)
        aggregator.invalidate(ws, we)  # 始终以最新清洗结果为准
        metric = aggregator.build(real_events, [], ws, we)

        # 环比对比（上一周期指标快照 → 本期）
        if history_events:
            prev = (history_events[0].extra or {}).get("prev_metrics")
            if prev:
                metric.trend["compare"] = cls._build_compare(prev, metric.to_dict())
        logger.info(f"[PIPE] 指标聚合完成: total={metric.alert.get('total', 0)} "
                    f"compare={'有' if metric.trend.get('compare') else '无'}")
        return metric

    @staticmethod
    def _build_compare(prev: dict, cur: dict) -> dict:
        """构建环比对比表（本期 vs 上期，含增量与百分比）"""

        def _delta(p, c):
            if p is None or p == 0:
                return f"{c}（无上期）" if c else "0"
            diff = round(c - p, 2)
            pct = round(diff / p * 100, 1)
            return f"{c}（{'+' if diff >= 0 else ''}{diff} / {pct:+.1f}%）"

        def _delta_rate(p, c):
            """百分比指标（close_rate 小数 0-1）"""
            if p is None or p == 0:
                return f"{c * 100:.1f}%（无上期）"
            diff = round(c - p, 4)
            pct = round(diff / p * 100, 1)
            return f"{c * 100:.1f}%（{'+' if diff >= 0 else ''}{diff * 100:.1f}pp / {pct:+.1f}%）"

        pa, ca = prev.get("alert", {}), cur.get("alert", {})
        pv, cv = prev.get("vuln", {}), cur.get("vuln", {})
        return {
            "alert_total": {"cur": ca.get("total", 0), "prev": pa.get("total", 0),
                            "delta": _delta(pa.get("total", 0), ca.get("total", 0))},
            "alert_high": {"cur": ca.get("high", 0), "prev": pa.get("high", 0),
                           "delta": _delta(pa.get("high", 0), ca.get("high", 0))},
            "close_rate": {"cur": ca.get("close_rate", 0), "prev": pa.get("close_rate", 0),
                           "delta": _delta_rate(pa.get("close_rate", 0), ca.get("close_rate", 0))},
            "unfixed_high": {"cur": cv.get("unfixed_high", 0), "prev": pv.get("unfixed_high", 0),
                             "delta": _delta(pv.get("unfixed_high", 0), cv.get("unfixed_high", 0))},
        }

    @classmethod
    async def _judge(cls, metric, cycle: str, ws: str, we: str):
        """双路研判：规则引擎 → RAG → LLM"""
        from capability.judge.rule_engine import build_default_engine
        from capability.judge.llm_judge import LLMJudge
        from capability.rag.rag_facade import RAGFacade

        engine = build_default_engine()
        flags = engine.evaluate_all(metric)
        composite = engine.composite_level(flags)

        facade = RAGFacade(enabled=True)
        refs = facade.recall_for_metric(metric) or []

        # 知识库关键词检索注入（V2.0 T1）：按指标告警/攻击类型匹配文档，替代全量注入
        kb_refs = cls._kb_refs(metric)
        if kb_refs:
            refs = refs + kb_refs
            logger.info(f"[PIPE] 知识库命中 {len(kb_refs)} 篇: {[r['kb_label'] for r in kb_refs]}")

        judge = LLMJudge()
        result = await judge.judge(metric, flags, refs)
        if result.risk_level == "LOW" and composite != "LOW":
            result.risk_level = composite
        logger.info(f"[PIPE] 研判完成: risk={result.risk_level} llm_ok={result.llm_ok}")
        return result

    @classmethod
    def _kb_refs(cls, metric) -> list[dict]:
        """知识库关键词检索（V2.0 T1）：按指标告警/攻击类型匹配文档"""
        try:
            from infra.db.session import SessionLocal
            from infra.db.repositories import KnowledgeDocRepo
            alert = metric.alert or {}
            top = metric.top or {}
            types = [
                (i.get("type") or "") for i in (top.get("top_type") or [])[:5]
            ] + [
                (i.get("attack_type") or "") for i in (alert.get("by_type") or [])[:5]
            ]
            keywords = [t for t in types if t] or ["安全", "攻击", "漏洞"]
            db = SessionLocal()
            try:
                docs = KnowledgeDocRepo.list_enabled(db, limit=20)
            finally:
                db.close()
            scored = []
            for d in docs:
                text = f"{d.title} {d.content}"
                score = sum(1 for kw in keywords if kw in text)
                if score:
                    scored.append((score, d))
            scored.sort(key=lambda x: -x[0])
            picked = [d for _, d in scored[:5]] or docs[:3]
            return [
                {"kb_label": f"知识库·{d.category}", "content": f"{d.title}：{d.content}"}
                for d in picked
            ]
        except Exception as e:
            logger.warning(f"[PIPE] 知识库检索失败（忽略）: {e}")
            return []

    @classmethod
    async def _render_and_snapshot(cls, task_id: int, cycle: str, ws: str, we: str,
                                   metric, judge, cleaned: list) -> dict:
        """渲染 md+docx → 版本快照 + 指标快照"""
        from capability.render.register import register_renderers
        register_renderers()
        from capability.render.render_base import RendererFactory
        from app.services.version_service import VersionService
        from infra.db.session import SessionLocal
        from infra.db.repositories import MetricSnapshotRepo
        from infra.storage import file_store
        from common.constant.constant import TITLE_TEMPLATE, EMPTY_REPORT_TITLE, EMPTY_REPORT_BODY
        from model.enum.enums import ReportCycle

        cycle_label = ReportCycle(cycle).label
        empty = metric.alert.get("total", 0) == 0 and metric.vuln.get("total", 0) == 0

        data = RenderData(
            cycle=cycle, cycle_label=cycle_label, window_start=ws, window_end=we,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            metric=metric.to_dict(), judge=judge.to_dict(),
            empty=empty,
            extra={"title": TITLE_TEMPLATE.format(cycle_label=cycle_label, window_start=ws[:10], window_end=we[:10])},
        )

        # 指标快照（溯源/对比）
        db = SessionLocal()
        try:
            snap = MetricSnapshotRepo.create(
                db, task_id=task_id, cycle=cycle, window_start=ws, window_end=we,
                metrics_json=metric.to_dict(),
            )
            snap_id = snap.id
        finally:
            db.close()

        md_renderer = RendererFactory.get("md")
        docx_renderer = RendererFactory.get("docx")
        md_path = file_store.build_report_path(cycle, version_no=1, ext="md")
        docx_path = file_store.build_report_path(cycle, version_no=1, ext="docx")

        if empty:
            md_content = f"# {EMPTY_REPORT_TITLE.format(cycle_label=cycle_label, window_start=ws[:10], window_end=we[:10])}\n\n{EMPTY_REPORT_BODY}"
        else:
            md_content = md_renderer.render(data)
        # 章节裁剪（报告选配 sections 开关，V1.3）
        md_content = cls._filter_sections(md_content, cls._load_report_sections())
        md_path = file_store.save_file(md_content, md_path)
        docx_path = docx_renderer.render_to_file(data, docx_path)

        version = VersionService.create_draft(
            task_id=task_id, cycle=cycle, window_start=ws, window_end=we,
            title=data.extra["title"], content_md=md_content,
            file_path=md_path, metric_snapshot_id=snap_id,
        )
        logger.info(f"[PIPE] 版本快照 #{version['id']}: {md_path}")
        return version

    # ── 报告选配辅助（V1.3） ──

    _SECTION_KEYWORDS = {
        "overview": "总体", "alert": "告警", "vuln": "漏洞",
        "attack": "攻击", "trend": "趋势", "suggestion": "建议",
    }

    @classmethod
    def _load_report_sections(cls) -> Optional[dict]:
        """读取报告选配章节开关（异常/未配置返回 None = 不裁剪）"""
        try:
            from infra.db.session import SessionLocal
            from infra.db.repositories import ReportConfigRepo
            db = SessionLocal()
            try:
                cfg = ReportConfigRepo.get_or_create(db)
                return cfg.sections or None
            finally:
                db.close()
        except Exception:
            return None

    @classmethod
    def _filter_sections(cls, content_md: str, sections: Optional[dict]) -> str:
        """按章节开关裁剪 markdown（关闭章节整段移除）"""
        if not sections or not content_md:
            return content_md
        lines = content_md.split("\n")
        out: list[str] = []
        drop = False
        for ln in lines:
            if ln.startswith("## "):
                title = ln[3:]
                key = next((k for k, kw in cls._SECTION_KEYWORDS.items() if kw in title), None)
                drop = bool(key) and not sections.get(key, True)
            if not drop:
                out.append(ln)
        return "\n".join(out)

    @classmethod
    def _auto_push_if_enabled(cls, version_id: int):
        """报告选配 auto_generate=enabled 时自动推送所有已选渠道"""
        try:
            from infra.db.session import SessionLocal
            from infra.db.repositories import ReportConfigRepo, PushLogRepo, ReportVersionRepo
            from capability.push.push_strategy import PushStrategyFactory
            from capability.push.local_strategy import LocalPushStrategy
            from capability.push.webhook_strategies import (
                DingTalkPushStrategy, WeComPushStrategy, EmailPushStrategy,
            )

            PushStrategyFactory.register(LocalPushStrategy)
            PushStrategyFactory.register(DingTalkPushStrategy)
            PushStrategyFactory.register(WeComPushStrategy)
            PushStrategyFactory.register(EmailPushStrategy)

            db = SessionLocal()
            try:
                cfg = ReportConfigRepo.get_or_create(db)
                if cfg.auto_generate != "enabled":
                    return
                ver = ReportVersionRepo.get(db, version_id)
                if not ver:
                    return
                version_info = {
                    "version_id": ver.id, "title": ver.title, "file_path": ver.file_path,
                    "content_md": ver.content_md, "cycle": ver.cycle, "version_no": ver.version_no,
                }
                for channel in (cfg.push_channels or ["local"]):
                    try:
                        strategy = PushStrategyFactory.get(channel)
                        result = strategy.push(version_info)
                        PushLogRepo.create(
                            db, version_id=version_id, channel=channel,
                            status="SUCCESS" if result.success else "FAILED",
                            detail=f"[自动推送] {result.detail[:360]}",
                        )
                        logger.info(f"[PIPE] 自动推送 #{version_id} → {channel}: "
                                    f"{'成功' if result.success else '失败'}")
                    except Exception as e:
                        logger.warning(f"[PIPE] 自动推送 {channel} 失败: {e}")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[PIPE] 自动推送流程异常（忽略）: {e}")

    # ── 状态收尾 ──

    @classmethod
    def _finish_task(cls, task_id: int, status: str, error: str = "",
                     duration_ms: int = 0, data_source_stats: Optional[dict] = None,
                     version_id: int = 0):
        from infra.db.session import SessionLocal
        from infra.db.repositories import ReportTaskRepo

        db = SessionLocal()
        try:
            task = ReportTaskRepo.get(db, task_id)
            if task:
                # V2.3 指标埋点：任务终态 + 耗时（埋点失败不影响业务）
                try:
                    from infra import metrics
                    metrics.inc("sec_report_task_total", {"status": status})
                    if status == TaskStatus.FAILED.value:
                        metrics.inc("sec_report_task_failed_total")
                    if duration_ms > 0:
                        metrics.inc("sec_report_task_duration_seconds_total",
                                    {"cycle": task.cycle}, value=max(1, int(duration_ms / 1000)))
                except Exception:
                    pass
                ReportTaskRepo.update(
                    db, task, status=status, error_msg=error,
                    finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    duration_ms=duration_ms,
                    data_source_stats=data_source_stats or {},
                )
        finally:
            db.close()


def run_report_task(cycle: str, trigger_type: str = "MANUAL",
                    window_start: str | None = None, window_end: str | None = None,
                    rerun: bool = False) -> dict:
    """同步入口（调度器/脚本调用）：内部 asyncio.run 执行"""
    from app.tasks.report_task import calc_window
    if not window_start or not window_end:
        window_start, window_end = calc_window(cycle)
    return asyncio.run(ReportService.generate(
        cycle, window_start, window_end, trigger_type=trigger_type, rerun=rerun,
    ))
