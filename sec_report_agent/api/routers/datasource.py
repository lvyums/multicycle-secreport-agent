"""数据源 API — 列表 / 连通测试"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.response import ok
from infra.db.session import get_db
from infra.db.repositories import DataSourceConfigRepo
from capability.adapter.factory import AdapterFactory
from common.exception.exception import NotFoundError

router = APIRouter()


@router.get("/list")
def datasource_list(db: Session = Depends(get_db)):
    """数据源配置列表（含适配器描述）"""
    rows = DataSourceConfigRepo.list_all(db)
    items = []
    for c in rows:
        try:
            adapter = AdapterFactory.get(c)
            desc = adapter.describe()
        except ValueError:
            desc = {"name": c.name, "type": c.type, "type_label": c.type,
                    "config": c.config_json, "status": c.status}
        desc.update({
            "id": c.id, "syncStrategy": c.sync_strategy,
            "filterRules": c.filter_rules_json, "description": c.description,
        })
        items.append(desc)
    return ok({"items": items})


@router.post("/test")
def datasource_test(body: dict, db: Session = Depends(get_db)):
    """测试数据源连通性（拉取 1 条验证）"""
    cfg_id = body.get("id")
    cfg = DataSourceConfigRepo.get(db, cfg_id) if cfg_id else None
    if not cfg:
        raise NotFoundError(f"数据源不存在: {cfg_id}")
    adapter = AdapterFactory.get(cfg)
    ok_flag, msg = adapter.test_connection()
    return ok({"id": cfg.id, "name": cfg.name, "ok": ok_flag, "message": msg})
