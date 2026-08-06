"""报告智能问答服务（V2.1）— 基于报告正文 + 知识库参考的 LLM 问答
设计：读版本正文 → RAG 召回知识库参考 → LLM 回答；
LLM 不可用（无 key/超时/异常）自动降级为正文关键词段落提取，不阻塞。
"""

from common.logger.logger import LogManager

logger = LogManager.get_logger()


class ReportQAService:
    """报告问答：读版本正文 → 召回知识库 → LLM 回答（降级：正文关键词提取）"""

    @staticmethod
    def _extract_snippet(content_md: str, question: str, limit: int = 350) -> str:
        """降级回答：中文安全关键词打分，返回最相关报告章节"""
        # 中文无空格分词，用领域关键词表匹配（而非按空格切词）
        KEYWORDS = ("高危", "中危", "低危", "告警", "攻击", "漏洞", "事件", "闭环", "趋势",
                    "预测", "建议", "态势", "威胁", "情报", "爆破", "注入", "木马", "处置")
        hits = [k for k in KEYWORDS if k in question]
        sections = [s.strip() for s in content_md.split("##") if s.strip()]
        # 问数量/告警类问题时优先态势或告警分析章节
        if any(k in question for k in ("多少", "几起", "数量", "告警", "事件")):
            for sec in sections:
                if "总体态势" in sec or "告警分析" in sec:
                    return sec[:limit]
        if hits:
            scored = sorted(
                sections,
                key=lambda s: -sum(1 for k in hits if k in s),
            )
            best = scored[0] if scored else ""
            if any(k in best for k in hits):
                return best[:limit]
        return (sections[0] if sections else content_md)[:limit]

    @classmethod
    async def ask(cls, db, version_id: int, question: str) -> dict:
        from common.exception.exception import NotFoundError
        from model.entity.entities import ReportVersion
        from capability.rag.rag_facade import RAGFacade
        from capability.judge.llm_factory import LLMFactory
        from config.settings import settings

        version = db.query(ReportVersion).filter(ReportVersion.id == version_id).first()
        if not version:
            raise NotFoundError(f"报告版本不存在: {version_id}")
        content_md = version.content_md or ""
        if not content_md.strip():
            return {"answer": "该版本无报告正文，暂无法问答。", "refs": [], "mode": "empty"}

        # 1) 知识库召回（参考材料，失败不阻塞）
        refs: list[dict] = []
        try:
            refs = RAGFacade().recall(question, top_k=3)
        except Exception as e:
            logger.debug(f"[QA] 知识库召回跳过: {e}")
        refs = refs[:3]

        # 2) LLM 回答
        try:
            ctx = content_md[: settings.llm_max_input_chars]
            kb_text = "\n".join(
                f"- [{r.get('kb_label') or r.get('kb_name')}] {str(r.get('content'))[:300]}" for r in refs
            )
            system = (
                "你是网络安全态势分析助手。基于给定的报告正文与参考资料，"
                "用简明、专业的中文回答分析师的问题；材料中没有的不要臆造。"
            )
            user = f"【报告正文】\n{ctx}\n\n【参考资料】\n{kb_text or '（无）'}\n\n【问题】{question}\n\n请回答："
            llm = await LLMFactory.get_light_llm()
            resp = await llm.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.2,
            )
            if resp.get("success") and resp.get("content"):
                return {"answer": str(resp["content"]).strip(), "refs": refs, "mode": "llm"}
            logger.warning(f"[QA] LLM 返回失败，降级提取: {resp.get('error')}")
        except Exception as e:
            logger.warning(f"[QA] LLM 调用异常，降级提取: {e}")

        # 3) 降级：正文关键词提取
        snippet = cls._extract_snippet(content_md, question)
        return {
            "answer": f"（LLM 服务暂不可用，已从报告中自动提取相关段落）\n\n{snippet}",
            "refs": refs,
            "mode": "fallback",
        }
