"""知识库台账(DB) ↔ 向量库(Chroma) 同步服务（V2.4.1）

背景：知识库页面管理 KnowledgeDoc(DB 台账)，而研判/问答召回走 Chroma 向量库。
此前两条链路割裂：页面加文档永远召回到(向量库空/旧 KB_FILE_MAP 未适配)。

本服务在 create/update/toggle/delete 时同步向量库：
  - 分类 → 向量库映射：attack/defense → threat_intel(威胁情报库)；
                           regulation/general → report_guideline(报告规范库)
  - 每条文档向量 id 固定为 doc_{id}，删除/禁用时按 id 精确移除
  - sync_all 供启动/手工全量重建（幂等：先清空再灌 enabled 文档）
"""
from common.logger.logger import LogManager

logger = LogManager.get_logger()

CATEGORY_KB = {
    "attack": "threat_intel",
    "defense": "threat_intel",
    "regulation": "report_guideline",
    "general": "report_guideline",
}


def _get_kb(kb_name: str):
    from capability.rag.rag_factory import RAGFactory
    return RAGFactory.get_kb(kb_name)


def _doc_text(doc) -> str:
    """向量化文本：标题 + 正文，标题优先提升命中率"""
    return f"{doc.title}\n{doc.content}"


def sync_add(doc) -> bool:
    """新增/更新单篇文档到向量库（幂等：同 id 覆盖）"""
    try:
        kb_name = CATEGORY_KB.get(doc.category, "report_guideline")
        kb = _get_kb(kb_name)
        kb.store.add_documents(
            documents=[_doc_text(doc)],
            metadatas=[{"source": doc.title, "category": doc.category, "doc_id": str(doc.id)}],
            ids=[f"doc_{doc.id}"],
        )
        return True
    except Exception as e:
        logger.error(f"[KB同步] 文档 {doc.id} 入库失败: {e}")
        return False


def sync_remove(doc_id: int) -> bool:
    """按文档 id 从向量库移除（跨库尝试，幂等）"""
    ok = False
    for kb_name in ("threat_intel", "report_guideline"):
        try:
            kb = _get_kb(kb_name)
            kb.store.delete([f"doc_{doc_id}"])
            ok = True
        except Exception:
            pass
    return ok


def sync_all(db) -> dict:
    """全量重建：清空两个业务库，按 DB 中 enabled 文档重灌（启动/修复用）"""
    from model.entity.entities import KnowledgeDoc

    stats = {}
    for kb_name in ("threat_intel", "report_guideline"):
        try:
            kb = _get_kb(kb_name)
            ids = kb.store._collection.get().get("ids") or []
            kb.store.delete(ids)
        except Exception as e:
            logger.warning(f"[KB同步] 清空 {kb_name} 失败: {e}")
    docs = db.query(KnowledgeDoc).filter(KnowledgeDoc.enabled == "enabled").all()
    for d in docs:
        if sync_add(d):
            stats[d.id] = d.title
    logger.info(f"[KB同步] 全量重建完成: {len(stats)}/{len(docs)} 篇入向量库")
    return stats
