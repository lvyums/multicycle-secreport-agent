"""向量库管理 — ChromaDB 封装（真实嵌入 + 多级降级）"""

import hashlib
import os
import re
from typing import Optional

import chromadb
from chromadb.api.types import EmbeddingFunction, Embeddings
from chromadb.config import Settings as ChromaSettings

from common.logger import LogManager

logger = LogManager.get_logger()


# ═══════════════════════════════════════════════════
# 第1级：Sentence-Transformer 嵌入（最佳效果）
# ═══════════════════════════════════════════════════

class BGEEmbeddingFunction(EmbeddingFunction):
    """基于 sentence-transformers 的 BGE 中文嵌入函数

    使用 settings 中配置的 EMBEDDING_MODEL（默认 BAAI/bge-large-zh-v1.5）。
    模型首次使用时会自动下载（约 1.3GB），后续从缓存加载。
    """

    # 类级别缓存：sentence_transformers 是否可用（避免重复 import 浪费 10s+）
    _st_available: Optional[bool] = None

    @staticmethod
    def _check_compatibility() -> bool:
        """快速检测 sentence_transformers 是否可用（不触发完整 import 链）"""
        # 检查已知的 Keras 3 不兼容问题
        try:
            import keras  # noqa: F401
            if hasattr(keras, '__version__') and keras.__version__.startswith('3.'):
                # Keras 3 + transformers 不兼容，需要安装 tf-keras
                try:
                    import tf_keras  # noqa: F401
                except ImportError:
                    return False
        except ImportError:
            pass  # 没有 keras，不受影响
        return True

    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        self.model_name = model_name
        self._model = None
        self._load_model()

    def _load_model(self):
        # 首次检测 sentence_transformers 是否可用，缓存结果
        if BGEEmbeddingFunction._st_available is None:
            if not self._check_compatibility():
                BGEEmbeddingFunction._st_available = False
                logger.info("sentence_transformers 环境不兼容（Keras 3 缺少 tf-keras），使用 N-gram 降级嵌入")
            else:
                try:
                    from sentence_transformers import SentenceTransformer  # noqa: F401
                    BGEEmbeddingFunction._st_available = True
                except Exception:
                    BGEEmbeddingFunction._st_available = False
                    logger.info("sentence_transformers 不可用，使用 N-gram 降级嵌入")

        if not BGEEmbeddingFunction._st_available:
            return

        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name,
                cache_folder=None,
            )
            dim = self._model.get_sentence_embedding_dimension()
            logger.info(f"✓ BGE 嵌入模型加载成功: {self.model_name} (维度: {dim})")
        except Exception as e:
            logger.warning(f"BGE 模型加载失败 ({e})，尝试轻量模型...")
            self._try_lightweight()

    def _try_lightweight(self):
        """第2级降级：轻量英文模型"""
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            dim = self._model.get_sentence_embedding_dimension()
            logger.info(f"⚠ 已降级到轻量模型: all-MiniLM-L6-v2 (维度: {dim})")
        except Exception as e:
            logger.error(f"轻量模型也加载失败: {e}")
            self._model = None

    def __call__(self, texts: list[str]) -> Embeddings:
        if self._model is not None:
            # BGE 建议在编码前加上 instruction 前缀以提高检索效果
            prefixed = [
                f"为这个句子生成表示以用于检索相关文章：{t}"[:512]
                for t in texts
            ]
            embeddings = self._model.encode(
                prefixed,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return embeddings.tolist()
        # 终极降级：N-gram 特征向量
        return NGramEmbeddingFunction()(texts)


# ═══════════════════════════════════════════════════
# 第3级降级：N-gram 特征向量（纯 Python，无依赖）
# ═══════════════════════════════════════════════════

class NGramEmbeddingFunction(EmbeddingFunction):
    """基于字符 N-gram 的特征向量

    不依赖任何外部模型或网络，仅使用 Python 标准库。
    虽然效果不如语义嵌入，但比 MD5 哈希有意义得多。
    """

    VECTOR_SIZE = 128
    NGRAM_RANGE = (2, 3)  # bigram + trigram

    def __call__(self, texts: list[str]) -> Embeddings:
        result = []
        for text in texts:
            vec = self._text_to_vector(text)
            result.append(vec)
        return result

    def _text_to_vector(self, text: str) -> list[float]:
        """将文本转换为 N-gram 频率向量"""
        text = text.lower()[:1000]  # 截断避免过长的文本
        ngram_counts = {}

        for n in range(self.NGRAM_RANGE[0], self.NGRAM_RANGE[1] + 1):
            for i in range(len(text) - n + 1):
                ngram = text[i:i + n]
                # 只保留中英文和数字的 n-gram
                if re.match(r'^[a-z0-9一-鿿]+$', ngram):
                    ngram_counts[ngram] = ngram_counts.get(ngram, 0) + 1

        if not ngram_counts:
            return [0.0] * self.VECTOR_SIZE

        # 取 TOP N 特征 + 哈希到固定维度
        top = sorted(ngram_counts.items(), key=lambda x: -x[1])[:self.VECTOR_SIZE]
        vec = [0.0] * self.VECTOR_SIZE
        for ngram, count in top:
            idx = int(hashlib.md5(ngram.encode()).hexdigest()[:8], 16) % self.VECTOR_SIZE
            vec[idx] += count / max(len(text), 1)

        # L2 归一化
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]

        return vec


class EmbeddingCache:
    """Embedding 结果 LRU 缓存 — 避免重复计算"""

    def __init__(self, maxsize: int = 1000):
        self._cache: dict[str, list[float]] = {}
        self._maxsize = maxsize

    def get(self, key: str) -> Optional[list[float]]:
        return self._cache.get(key)

    def set(self, key: str, embedding: list[float]):
        if len(self._cache) >= self._maxsize:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = embedding

    def clear(self):
        self._cache.clear()


# ═══════════════════════════════════════════════════
# VectorStore — 对外封装
# ═══════════════════════════════════════════════════

# 已知的嵌入维度映射（用于 ChromaDB 集合兼容性检查）
KNOWN_DIMENSIONS = {
    "BAAI/bge-large-zh-v1.5": 1024,
    "BAAI/bge-small-zh-v1.5": 512,
    "all-MiniLM-L6-v2": 384,
    "ngram_fallback": 128,
    "md5_fallback": 16,
}


def get_embedding_function(model_name: Optional[str] = None) -> EmbeddingFunction:
    """创建嵌入函数（带自动降级）"""
    if model_name and model_name not in ("", "none"):
        return BGEEmbeddingFunction(model_name)
    # 尝试默认模型
    try:
        return BGEEmbeddingFunction("BAAI/bge-large-zh-v1.5")
    except Exception:
        try:
            return BGEEmbeddingFunction("all-MiniLM-L6-v2")
        except Exception:
            logger.warning("⚠ 所有 sentence-transformers 模型加载失败，使用 N-gram 降级嵌入")
            return NGramEmbeddingFunction()


class VectorStore:
    """向量库管理，封装 ChromaDB 基本操作"""

    # 类级别共享客户端 — 避免多个 PersistentClient 竞争 SQLite 锁
    _shared_client: Optional[chromadb.PersistentClient] = None
    _shared_client_dir: Optional[str] = None

    def __init__(self, collection_name: str, persist_dir: str,
                 embedding_model: Optional[str] = None):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self.embed_fn = get_embedding_function(embedding_model)
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None
        self._init_client()

    def _get_target_dimension(self) -> int:
        """获取当前嵌入函数的输出维度"""
        # 尝试从已知映射获取
        for key, dim in KNOWN_DIMENSIONS.items():
            if key in str(type(self.embed_fn).__name__):
                return dim
        # 试跑一次推断
        try:
            test = self.embed_fn(["test"])
            if test and len(test[0]) > 0:
                return len(test[0])
        except Exception:
            pass
        return 128  # 默认

    def _init_client(self):
        """初始化 ChromaDB 客户端并加载集合

        使用类级别共享客户端避免多个 PersistentClient 竞争 SQLite 锁。
        主路径被锁时自动切换到备用路径。
        """
        self._client = self._get_or_create_shared_client(self.persist_dir)
        if self._client is None:
            import tempfile
            fallback = os.path.join(tempfile.gettempdir(), "chroma_db_fallback")
            logger.warning(f"主路径 {self.persist_dir} 不可用，切换到备用路径: {fallback}")
            self._client = self._get_or_create_shared_client(fallback)
        if self._client is None:
            raise RuntimeError("ChromaDB 客户端初始化失败，主路径和备用路径均不可用")

        try:
            collection = self._client.get_collection(
                self.collection_name,
                embedding_function=self.embed_fn,
            )
            if self._check_dimension_mismatch(collection):
                logger.warning(f"集合 {self.collection_name} 嵌入维度不匹配，重建中...")
                self._client.delete_collection(self.collection_name)
                self._collection = self._client.create_collection(
                    self.collection_name,
                    embedding_function=self.embed_fn,
                )
            else:
                self._collection = collection
                logger.info(f"加载已有集合: {self.collection_name}")
        except Exception:
            try:
                self._client.delete_collection(self.collection_name)
            except Exception:
                pass
            self._collection = self._client.create_collection(
                self.collection_name,
                embedding_function=self.embed_fn,
            )
            logger.info(f"创建新集合: {self.collection_name}")

    @classmethod
    def _get_or_create_shared_client(cls, path: str) -> Optional[chromadb.PersistentClient]:
        """获取或创建共享的 ChromaDB 客户端（单例模式）"""
        if cls._shared_client is not None and cls._shared_client_dir == path:
            logger.debug(f"复用共享 ChromaDB 客户端: {path}")
            return cls._shared_client

        client = cls._try_create_client(path)
        if client is not None:
            cls._shared_client = client
            cls._shared_client_dir = path
        return client

    @staticmethod
    def _try_create_client(path: str) -> Optional[chromadb.PersistentClient]:
        """创建 ChromaDB 客户端，检测并清理锁文件避免僵尸进程阻塞"""
        db_file = os.path.join(path, "chroma.sqlite3")
        journal = db_file + "-journal"

        # 检测并清理残留锁文件
        for f in [journal, db_file]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                    logger.info(f"清理残留文件: {f}")
                except OSError:
                    logger.warning(f"数据库被其他进程锁定，跳过: {path}")
                    return None

        try:
            return chromadb.PersistentClient(
                path=path,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        except Exception as e:
            logger.warning(f"ChromaDB 客户端创建失败: {e}")
            return None

    def _check_dimension_mismatch(self, collection) -> bool:
        """检查集合的嵌入维度是否与当前嵌入函数匹配"""
        try:
            # 如果集合有数据，检查第一条数据的维度
            count = collection.count()
            if count == 0:
                return False  # 空集合不需要重建

            # 尝试一次查询来检查维度兼容性
            collection.query(query_texts=["test"], n_results=1)
            return False  # 查询成功，维度匹配
        except Exception as e:
            error_msg = str(e).lower()
            if "dimension" in error_msg or "dimensionality" in error_msg:
                logger.warning(f"维度不匹配，需要重建集合: {e}")
                return True
            logger.warning(f"集合检查异常（忽略）: {e}")
            return False

    def add_documents(self, documents: list[str], metadatas: list[dict], ids: list[str]):
        """添加文档到向量库"""
        if not documents:
            return
        try:
            self._collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
        except Exception as e:
            logger.error(f"添加文档失败: {e}")

    def similarity_search(self, query: str, k: int = 5,
                          score_threshold: float = 0.0) -> list[dict]:
        """向量检索 + 过滤低分结果"""
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=k,
            )
            items = []
            distances = results.get("distances", [[]])[0] if results.get("distances") else []
            documents = results.get("documents", [[]])[0] if results.get("documents") else []
            metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
            ids = results.get("ids", [[]])[0] if results.get("ids") else []

            for i, doc in enumerate(documents):
                # ChromaDB 返回的是 L2 距离，转为相似度分数
                score = 1.0 - (distances[i] / 2.0) if i < len(distances) else 0.0
                score = max(0.0, min(1.0, score))
                if score >= score_threshold:
                    items.append({
                        "id": ids[i] if i < len(ids) else "",
                        "document": doc,
                        "metadata": metadatas[i] if i < len(metadatas) else {},
                        "score": round(score, 4),
                    })
            return items
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []

    def count(self) -> int:
        """返回集合中文档数量"""
        try:
            return self._collection.count()
        except Exception:
            return 0