"""告警规则 API（V2.4）— admin 热更新阈值/开关，无需重启"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth_deps import require_admin
from api.response import ok
from infra.db.repositories import AlertRuleRepo
from infra.db.session import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/alert", tags=["alert"])


class AlertRuleUpdate(BaseModel):
    threshold: float = Field(ge=0, le=100000)
    enabled: str = Field(pattern="^(enabled|disabled)$")


def _to_dict(r):
    return {
        "id": r.id, "ruleKey": r.rule_key, "name": r.name,
        "threshold": r.threshold, "windowHours": r.window_hours,
        "enabled": r.enabled, "updatedAt": r.updated_at, "updatedBy": r.updated_by,
    }


@router.get("/rules")
def list_rules(_=Depends(require_admin), db: Session = Depends(get_db)):
    rules = AlertRuleRepo.list_all(db)
    return ok(data={"items": [_to_dict(r) for r in rules]})


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: AlertRuleUpdate, user=Depends(require_admin),
                db: Session = Depends(get_db)):
    rule = AlertRuleRepo.update(db, rule_id, threshold=body.threshold,
                                enabled=body.enabled, updated_by=user.username)
    if rule is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="规则不存在")
    return ok(data=_to_dict(rule))
