"""RAG 知识库工厂 — 分片管理 + 路由检索"""

from dataclasses import dataclass, field
from typing import Optional

from infra.vector.vector_store import VectorStore
from common.logger import LogManager

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

    # 知识库注册表
    KB_REGISTRY: dict[str, dict] = {
        "log_basics": {"label": "日志基础库", "description": "全类型日志字段释义、正常/异常行为特征"},
        "compliance": {"label": "合规审计库", "description": "等保2.0、网安法、数据安全法"},
        "collection": {"label": "采集架构库", "description": "多设备采集协议、配置规范、架构方案"},
        "scripts": {"label": "技术脚本库", "description": "攻击正则、检索语法、清洗规则"},
        "cases": {"label": "实训案例库", "description": "标准化攻防场景、任务流程"},
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