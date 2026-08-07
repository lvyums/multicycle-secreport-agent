"""知识库 API — 文档 CRUD / 分类 / 启停（V1.3，研判参考注入源）"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.response import ok
from api.auth_deps import require_login, require_admin, require_analyst
from infra.db.session import get_db
from infra.db.repositories import KnowledgeDocRepo
from common.exception.exception import BusinessError, NotFoundError

router = APIRouter()

CATEGORIES = ["general", "attack", "defense", "regulation"]


@router.get("/categories")
def kb_categories(_=Depends(require_login)):
    return ok({"categories": CATEGORIES})


@router.get("/list")
def kb_list(category: str = "", _=Depends(require_login), db: Session = Depends(get_db)):
    """知识库文档列表（可按分类筛选）"""
    rows = KnowledgeDocRepo.list_all(db, category or None)
    items = [{
        "id": d.id, "title": d.title, "category": d.category,
        "content": d.content, "enabled": d.enabled,
        "createdAt": d.created_at, "updatedAt": d.updated_at,
    } for d in rows]
    return ok({"items": items})


@router.post("/create")
def kb_create(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    title = (body.get("title") or "").strip()
    if not title:
        raise BusinessError("标题必填")
    category = (body.get("category") or "general").strip()
    if category not in CATEGORIES:
        raise BusinessError(f"非法分类: {category}")
    doc = KnowledgeDocRepo.create(
        db,
        title=title,
        category=category,
        content=body.get("content", ""),
        enabled=body.get("enabled", "enabled"),
    )
    if doc.enabled == "enabled":
        from capability.rag.kb_sync import sync_add
        sync_add(doc)
    return ok({"id": doc.id, "title": doc.title})


@router.post("/update")
def kb_update(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    doc = KnowledgeDocRepo.get(db, body.get("id") or 0)
    if not doc:
        raise NotFoundError(f"文档不存在: {body.get('id')}")
    if body.get("category") and body["category"] not in CATEGORIES:
        raise BusinessError(f"非法分类: {body['category']}")
    KnowledgeDocRepo.update(
        db, doc,
        title=body.get("title", doc.title),
        category=body.get("category", doc.category),
        content=body.get("content", doc.content),
    )
    from capability.rag.kb_sync import sync_add, sync_remove
    sync_remove(doc.id)
    if doc.enabled == "enabled":
        sync_add(doc)
    return ok({"id": doc.id})


@router.post("/toggle")
def kb_toggle(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    doc = KnowledgeDocRepo.get(db, body.get("id") or 0)
    if not doc:
        raise NotFoundError(f"文档不存在: {body.get('id')}")
    KnowledgeDocRepo.toggle(db, doc)
    from capability.rag.kb_sync import sync_add, sync_remove
    if doc.enabled == "enabled":
        sync_add(doc)
    else:
        sync_remove(doc.id)
    return ok({"id": doc.id, "enabled": doc.enabled})


@router.post("/delete")
def kb_delete(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    doc = KnowledgeDocRepo.get(db, body.get("id") or 0)
    if not doc:
        raise NotFoundError(f"文档不存在: {body.get('id')}")
    KnowledgeDocRepo.delete(db, doc)
    from capability.rag.kb_sync import sync_remove
    sync_remove(doc.id)
    return ok({"id": body.get("id")})
