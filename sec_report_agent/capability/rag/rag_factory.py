"""RAG 知识库工厂 — 分片管理 + 路由检索"""

from dataclasses import dataclass, field
from typing import Optional

from infra.vector.vector_store import VectorStore
from common.logger.logger import LogManager

logger = LogManager.get_logger()


@dataclass
class RetrievalResult:
    """检索结果"""
    query: str
    items: list[dict] = field(default_factory=list)
    total: int = 0
    kb_name: str = ""
    kb_label: str = ""


class KnowledgeBase:
    """单个知识库分片"""

    def __init__(self, kb_name: str, kb_label: str, persist_dir: str,
                 embedding_model: Optional[str] = None):
        self.kb_name = kb_name
        self.kb_label = kb_label
        self.store = VectorStore(
            collection_name=kb_name,
            persist_dir=persist_dir,
            embedding_model=embedding_model,
        )

    def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        """检索知识库"""
        items = self.store.similarity_search(query, k=top_k)
        return RetrievalResult(
            query=query, items=items, total=len(items),
            kb_name=self.kb_name, kb_label=self.kb_label,
        )

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """Cross-encoder 重排序（当前返回原顺序，后续接入 reranker 模型）"""
        return sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)


class RAGFactory:
    """RAG 知识库工厂 — 管理所有知识库分片，支持按需路由"""

    # 知识库注册表（报告场景）
    KB_REGISTRY: dict[str, dict] = {
        "report_guideline": {"label": "报告规范库", "description": "网安态势报告撰写规范、章节结构、术语口径"},
        "threat_intel": {"label": "威胁情报库", "description": "漏洞情报、攻击手法、威胁家族特征"},
        "history": {"label": "历史报告库", "description": "历史周期报告沉淀，供趋势对比与风格参考"},
    }

    _instances: dict[str, KnowledgeBase] = {}

    @classmethod
    def get_kb(cls, kb_name: str) -> KnowledgeBase:
        """返回指定知识库实例（单例）"""
        if kb_name not in cls.KB_REGISTRY:
            raise ValueError(f"未知知识库: {kb_name}，可用: {list(cls.KB_REGISTRY.keys())}")

        if kb_name not in cls._instances:
            from config.settings import settings
            cls._instances[kb_name] = KnowledgeBase(
                kb_name=kb_name,
                kb_label=cls.KB_REGISTRY[kb_name]["label"],
                persist_dir=settings.chroma_db_path,
                embedding_model=settings.embedding_model,
            )
        return cls._instances[kb_name]

    @classmethod
    def retrieve(cls, kb_name: str, query: str, top_k: int = 5) -> RetrievalResult:
        """按知识库分片名称检索（统一入口，模块二/三/四直接复用）"""
        kb = cls.get_kb(kb_name)
        return kb.retrieve(query, top_k=top_k)

    @classmethod
    def get_available_kbs(cls) -> list[str]:
        """获取所有可用知识库名称"""
        return list(cls.KB_REGISTRY.keys())

    @classmethod
    def get_kb_label(cls, kb_name: str) -> str:
        """获取知识库中文名称"""
        info = cls.KB_REGISTRY.get(kb_name)
        return info["label"] if info else kb_name