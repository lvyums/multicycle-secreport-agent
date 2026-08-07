"""V2.4.1 知识库↔向量库同步测试 — 防回归（台账 CRUD 后向量库必须联动）"""

from types import SimpleNamespace

import pytest


class FakeStore:
    """内存向量库替身：记录 add/delete，验证同步逻辑"""
    def __init__(self):
        self.docs = {}
        self.deleted = []

    def add_documents(self, documents, metadatas, ids):
        for i, doc_id in enumerate(ids):
            self.docs[doc_id] = {"text": documents[i], "meta": metadatas[i]}

    def delete(self, ids):
        for doc_id in ids:
            self.docs.pop(doc_id, None)
            self.deleted.append(doc_id)

    def count(self):
        return len(self.docs)


@pytest.fixture()
def fake_kb(monkeypatch):
    stores = {"threat_intel": FakeStore(), "report_guideline": FakeStore()}

    class FakeKB:
        def __init__(self, name):
            self.name = name
            self.store = stores[name]

    def fake_get_kb(kb_name):
        return FakeKB(kb_name)

    from capability.rag import rag_factory
    monkeypatch.setattr(rag_factory.RAGFactory, "get_kb", staticmethod(fake_get_kb))
    return stores


def _doc(doc_id=101, category="attack", title="测试暴力破解文档", enabled="enabled"):
    return SimpleNamespace(
        id=doc_id, title=title, category=category,
        content="暴力破解攻击特征与处置建议：封禁源IP、启用MFA、弱口令整改、登录限流。",
        enabled=enabled,
    )


def test_sync_add_attack_goes_threat_intel(fake_kb):
    from capability.rag.kb_sync import sync_add
    assert sync_add(_doc())
    store = fake_kb["threat_intel"]
    assert store.count() == 1
    assert "doc_101" in store.docs
    assert "测试暴力破解文档" in store.docs["doc_101"]["text"]
    assert store.docs["doc_101"]["meta"]["source"] == "测试暴力破解文档"
    assert fake_kb["report_guideline"].count() == 0


def test_sync_add_regulation_goes_report_guideline(fake_kb):
    from capability.rag.kb_sync import sync_add
    sync_add(_doc(doc_id=202, category="regulation", title="指标口径文档"))
    store = fake_kb["report_guideline"]
    assert store.count() == 1
    assert "doc_202" in store.docs


def test_sync_remove_across_both_kbs(fake_kb):
    from capability.rag.kb_sync import sync_add, sync_remove
    sync_add(_doc(doc_id=303, category="attack"))
    sync_add(_doc(doc_id=303, category="regulation"))  # 同一 id 跨库场景
    sync_remove(303)
    assert fake_kb["threat_intel"].count() == 0
    assert fake_kb["report_guideline"].count() == 0
    assert "doc_303" in fake_kb["threat_intel"].deleted


def test_sync_all_rebuilds_from_enabled_docs(fake_kb, monkeypatch):
    from capability.rag.kb_sync import sync_all

    class FakeRepo:
        @staticmethod
        def query(cls):
            return FakeQuery()

    class FakeQuery:
        def filter(self, cond):
            return self

        def all(self):
            # 模拟 SQLAlchemy WHERE enabled='enabled' 过滤
            return [d for d in [
                _doc(doc_id=1, category="attack"),
                _doc(doc_id=2, category="regulation", title="报告规范"),
                _doc(doc_id=3, category="attack", enabled="disabled"),  # 停用不入库
            ] if d.enabled == "enabled"]

    import model.entity.entities as entities_mod
    monkeypatch.setattr(entities_mod, "KnowledgeDoc",
                        type("KnowledgeDoc", (), {"enabled": "enabled"}))
    db = SimpleNamespace(query=FakeRepo.query)
    stats = sync_all(db)
    assert len(stats) == 2  # 只统计 enabled
    assert fake_kb["threat_intel"].count() == 1
    assert fake_kb["report_guideline"].count() == 1
