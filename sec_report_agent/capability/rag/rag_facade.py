"""RAG 召回外观 — 研判前召回知识库参考（V1.1 知识库可空，优雅降级）

设计：报告场景三个知识库分片（报告规范/威胁情报/历史报告）；
知识库未灌入/向量库不可用时返回空引用，不阻塞报告生成。
"""

from typing import Optional

from common.logger.logger import LogManager

logger = LogManager.get_logger()


class RAGFacade:
    """RAG 召回外观"""

    def __init__(self, enabled: bool = True):
        self._enabled = enabled

    def recall(self, query: str, kb_names: Optional[list[str]] = None, top_k: int = 3) -> list[dict]:
        """按知识库分片召回参考文档"""
        if not self._enabled:
            return []
        try:
            from capability.rag.rag_factory import RAGFactory
            targets = kb_names or list(RAGFactory.KB_REGISTRY.keys())
            refs: list[dict] = []
            for kb in targets:
                try:
                    result = RAGFactory.retrieve(kb, query, top_k=top_k)
                    for item in result.items:
                        meta = item.get("metadata") or {}
                        refs.append({
                            "kb_name": result.kb_name,
                            "kb_label": result.kb_label,
                            "title": meta.get("source") or "",
                            "content": item.get("document") or item.get("text") or "",
                            "score": item.get("score", 0),
                        })
                except Exception as e:
                    logger.debug(f"[RAG] 知识库 {kb} 检索跳过: {e}")
            return refs[:top_k * len(targets)]
        except Exception as e:
            logger.debug(f"[RAG] 召回服务不可用: {e}")
            return []

    def recall_for_metric(self, metric) -> list[dict]:
        """按指标摘要召回（研判 Prompt 的参考材料）"""
        alert = metric.alert or {}
        top = metric.top or {}
        query_parts = [
            f"{metric.cycle} 网络安全态势",
            f"高危告警 {alert.get('high', 0)} 起",
            f"TOP攻击类型 {', '.join((i.get('type') or '') for i in (top.get('top_type') or [])[:3])}",
        ]
        return self.recall(" ".join(query_parts), top_k=2)
