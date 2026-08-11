"""数据源 API — 列表 / 连通测试 / 零代码 CRUD（V1.3）"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.response import ok
from api.auth_deps import require_login, require_admin, require_analyst
from infra.db.session import get_db
from infra.db.repositories import DataSourceConfigRepo
from capability.adapter.factory import AdapterFactory
from capability.adapter.meta import TYPE_META
from common.exception.exception import BusinessError, NotFoundError

router = APIRouter()


@router.get("/meta")
def datasource_meta(_=Depends(require_login)):
    """数据源类型元数据（零代码表单驱动）"""
    return ok({"types": TYPE_META})


@router.get("/list")
def datasource_list(_=Depends(require_login), db: Session = Depends(get_db)):
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


@router.post("/create")
def datasource_create(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    """新建数据源（零代码表单提交）"""
    name = (body.get("name") or "").strip()
    stype = (body.get("type") or "").strip().upper()
    if not name or not stype:
        raise BusinessError("name 与 type 必填")
    if stype not in TYPE_META:
        raise BusinessError(f"不支持的数据源类型: {stype}")
    if DataSourceConfigRepo.get_by_name(db, name):
        raise BusinessError(f"数据源名称已存在: {name}")
    cfg = DataSourceConfigRepo.create(
        db,
        name=name,
        type=stype,
        status=body.get("status", "enabled"),
        config_json=body.get("config", {}) or {},
        filter_rules_json=body.get("filterRules", {}) or {},
        sync_strategy=body.get("syncStrategy", "window"),
        description=body.get("description", ""),
    )
    return ok({"id": cfg.id, "name": cfg.name})


@router.post("/update")
def datasource_update(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    """更新数据源配置"""
    cfg = DataSourceConfigRepo.get(db, body.get("id") or 0)
    if not cfg:
        raise NotFoundError(f"数据源不存在: {body.get('id')}")
    DataSourceConfigRepo.update(
        db, cfg,
        config_json=body.get("config", cfg.config_json),
        filter_rules_json=body.get("filterRules", cfg.filter_rules_json),
        sync_strategy=body.get("syncStrategy", cfg.sync_strategy),
        description=body.get("description", cfg.description),
    )
    return ok({"id": cfg.id, "name": cfg.name})


@router.post("/toggle")
def datasource_toggle(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    """启停数据源"""
    cfg = DataSourceConfigRepo.get(db, body.get("id") or 0)
    if not cfg:
        raise NotFoundError(f"数据源不存在: {body.get('id')}")
    DataSourceConfigRepo.toggle(db, cfg)
    return ok({"id": cfg.id, "status": cfg.status})


@router.post("/delete")
def datasource_delete(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    """删除数据源"""
    cfg = DataSourceConfigRepo.get(db, body.get("id") or 0)
    if not cfg:
        raise NotFoundError(f"数据源不存在: {body.get('id')}")
    DataSourceConfigRepo.delete(db, cfg)
    return ok({"id": body.get("id")})


@router.post("/test")
def datasource_test(body: dict, _=Depends(require_admin), db: Session = Depends(get_db)):
    """测试数据源连通性（拉取 1 条验证）"""
    cfg_id = body.get("id")
    cfg = DataSourceConfigRepo.get(db, cfg_id) if cfg_id else None
    if not cfg:
        raise NotFoundError(f"数据源不存在: {cfg_id}")
    adapter = AdapterFactory.get(cfg)
    ok_flag, msg = adapter.test_connection()
    return ok({"id": cfg.id, "name": cfg.name, "ok": ok_flag, "message": msg})


@router.get("/health")
def datasource_health(db: Session = Depends(get_db), _=Depends(require_login)):
    """数据源健康看板（V2.8）：按数据源聚合最近 N 次拉取结果（ok/条数/延迟）"""
    from model.entity.entities import ReportTask

    rows = DataSourceConfigRepo.list_all(db)
    cfgs = {c.name: c for c in rows}

    # 最近 30 个终态任务的拉取统计
    recent = (db.query(ReportTask)
              .filter(ReportTask.status.in_(["SUCCESS", "EMPTY", "PARTIAL", "FAILED"]))
              .order_by(ReportTask.id.desc())
              .limit(30)
              .all())

    agg: dict[str, dict] = {}
    for t in recent:
        stats = t.data_source_stats or {}
        for name, st in stats.items():
            a = agg.setdefault(name, {
                "name": name, "totalRuns": 0, "okRuns": 0, "failRuns": 0,
                "okRatio": 0.0, "latestOk": None, "latestCount": 0,
                "latestAt": None, "latestError": "", "type": st.get("type", ""),
            })
            a["totalRuns"] += 1
            if st.get("ok"):
                a["okRuns"] += 1
            else:
                a["failRuns"] += 1
            a["latestOk"] = st.get("ok")
            a["latestCount"] = st.get("count", 0)
            a["latestAt"] = t.finished_at or t.created_at
            a["latestError"] = st.get("error", "") or a["latestError"]
    for a in agg.values():
        a["okRatio"] = round(a["okRuns"] / a["totalRuns"], 2) if a["totalRuns"] else 0.0
        a["status"] = ("ok" if a["okRatio"] == 1.0
                       else ("warning" if a["okRatio"] > 0 else "error"))
        if not a["totalRuns"]:
            a["status"] = "unknown"

    # 合并配置表（无记录 → unknown）
    items = []
    for name, c in cfgs.items():
        if name in agg:
            item = agg[name]
            item["typeLabel"] = (TYPE_META.get(c.type, {}).get("label") or c.type)
            item["enabled"] = c.status
            items.append(item)
        else:
            items.append({
                "name": name, "type": c.type,
                "typeLabel": TYPE_META.get(c.type, {}).get("label") or c.type,
                "enabled": c.status, "totalRuns": 0, "okRuns": 0, "failRuns": 0,
                "okRatio": 0.0, "latestOk": None, "latestCount": 0,
                "latestAt": None, "latestError": "", "status": "unknown",
            })
    # 曾出现但已删除配置的数据源也列出（历史统计）
    for name, a in agg.items():
        if name not in cfgs:
            a["typeLabel"] = a["type"]
            a["enabled"] = "-"
            items.append(a)
    return ok({"items": items, "recentTasks": len(recent)})
