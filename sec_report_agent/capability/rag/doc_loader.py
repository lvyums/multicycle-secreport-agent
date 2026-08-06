"""知识库数据导入 — 将 rule_data JSON 向量化写入 ChromaDB"""

import json
import os
from typing import Optional

from capability.rag.rag_factory import RAGFactory
from common.logger import LogManager

logger = LogManager.get_logger()

# ── 知识库 → 数据文件映射 ──
KB_FILE_MAP: dict[str, list[str]] = {
    "log_basics": [
        "log_features.json",
        "risk_rules.json",
    ],
    "compliance": [
        "compliance_standards.json",
        "compliance_baselines.json",
    ],
    "collection": [
        "collect_templates.json",
        "device_protocol.json",
        "arch_templates.json",
    ],
    "scripts": [
        "script_gen_regex.json",
        "script_gen_es_queries.json",
        "script_gen_trace_patterns.json",
        "script_gen_fallback_rules.json",
        "script_gen_scoring.json",
        "script_gen_scene_keywords.json",
        "script_gen_platforms.json",
        "script_gen_platform_fallback.json",
        "script_gen_time_map.json",
    ],
    "cases": [
        "training_scenarios.json",
        "training_standard_answers.json",
        "fault_kb.json",
        "correlation_patterns.json",
    ],
}


def _chunk_text(text: str, max_len: int = 500) -> list[str]:
    """将长文本按段落/句子切分为不超过 max_len 的片段"""
    if len(text) <= max_len:
        return [text]
    chunks = []
    parts = text.split("\n")
    buf = ""
    for part in parts:
        if len(buf) + len(part) + 1 > max_len and buf:
            chunks.append(buf.strip())
            buf = part
        else:
            buf = buf + "\n" + part if buf else part
    if buf.strip():
        chunks.append(buf.strip())
    return chunks if chunks else [text[:max_len]]


def _flatten_json(data, prefix: str = "",
                  source_file: str = "") -> list[tuple[str, dict]]:
    """将 JSON 数据展平为 (text, metadata) 列表"""
    results = []

    if isinstance(data, list):
        for i, item in enumerate(data):
            results.extend(_flatten_json(item, prefix=f"{prefix}[{i}]",
                                         source_file=source_file))
    elif isinstance(data, dict):
        text_fields = []
        meta = {"source": source_file} if source_file else {}
        for k, v in data.items():
            if k in ("description", "detail", "requirement", "fault_desc",
                      "content", "name", "title", "scenario_id", "item_id",
                      "standard_id", "rule_id", "fault_type", "check_method",
                      "risk_if_not", "possible_causes", "fix_steps",
                      "prevention", "steps", "notes", "objectives", "hint"):
                if isinstance(v, str):
                    text_fields.append(f"{k}: {v}")
                elif isinstance(v, list):
                    text_fields.append(f"{k}: {'; '.join(str(x) for x in v)}")
            if k in ("scenario_id", "item_id", "standard_id", "rule_id",
                      "fault_type", "severity", "category", "difficulty",
                      "protocol", "device_type", "name"):
                meta[k] = str(v) if not isinstance(v, (str, int, float, bool)) else v

        if text_fields:
            text = "\n".join(text_fields)
            for chunk in _chunk_text(text):
                results.append((chunk, meta))
        else:
            for k, v in data.items():
                results.extend(_flatten_json(v, prefix=f"{prefix}.{k}",
                                             source_file=source_file))
    elif isinstance(data, str) and len(data) > 10:
        meta = {"source": source_file} if source_file else {"source": "unknown"}
        results.append((data, meta))

    return results


def _load_json_file(filepath: str) -> list[tuple[str, dict]]:
    """读取单个 JSON 文件并展平为 (text, metadata) 列表"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"读取 {filepath} 失败: {e}")
        return []

    source_file = os.path.basename(filepath)
    items = _flatten_json(data, source_file=source_file)
    if not items:
        logger.warning(f"{filepath} 展平后无有效文本")
    return items


def ingest_kb(kb_name: str, rule_data_dir: str,
              force: bool = False) -> int:
    """将指定知识库对应的 JSON 文件导入 ChromaDB"""
    files = KB_FILE_MAP.get(kb_name)
    if not files:
        logger.warning(f"未知知识库: {kb_name}")
        return 0

    kb = RAGFactory.get_kb(kb_name)

    # force 模式：删除空集合以避免嵌入函数不匹配
    if force and kb.store.count() == 0:
        try:
            kb.store._client.delete_collection(kb_name)
            kb.store._collection = kb.store._client.create_collection(
                kb_name, embedding_function=kb.store.embed_fn,
            )
            logger.info(f"重建空集合: {kb_name}")
        except Exception:
            pass

    # 已有数据则跳过
    if not force and kb.store.count() > 0:
        logger.info(f"知识库 {kb_name} 已有 {kb.store.count()} 条数据，跳过")
        return kb.store.count()

    all_items = []
    for fname in files:
        fpath = os.path.join(rule_data_dir, fname)
        items = _load_json_file(fpath)
        logger.info(f"  {fname} → {len(items)} 条")
        all_items.extend(items)

    if not all_items:
        logger.warning(f"知识库 {kb_name} 无数据可导入")
        return 0

    # ChromaDB 要求 metadata 为非空 dict，确保每条都有 source
    for text, meta in all_items:
        if not meta:
            meta["source"] = "unknown"

    documents = [text for text, _ in all_items]
    metadatas = [meta for _, meta in all_items]
    ids = [f"{kb_name}_{i}" for i in range(len(all_items))]

    batch_size = 100
    for start in range(0, len(documents), batch_size):
        end = start + batch_size
        kb.store.add_documents(
            documents=documents[start:end],
            metadatas=metadatas[start:end],
            ids=ids[start:end],
        )

    total = kb.store.count()
    logger.info(f"✓ 知识库 {kb_name} 导入完成: {total} 条")
    return total


def ingest_all(rule_data_dir: str, force: bool = False) -> dict[str, int]:
    """导入所有知识库，返回各库导入数量"""
    results = {}
    for kb_name in KB_FILE_MAP:
        try:
            count = ingest_kb(kb_name, rule_data_dir, force=force)
            results[kb_name] = count
        except Exception as e:
            logger.error(f"知识库 {kb_name} 导入失败: {e}")
            results[kb_name] = 0
    return results
