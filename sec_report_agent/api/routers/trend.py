"""趋势分析与报告时间轴 API（V2.6）— 查看趋势序列 / 五周期总览 / 报告时间轴"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.auth_deps import require_login
from api.response import ok
from app.services.trend_service import TrendService
from infra.db.session import get_db

router = APIRouter(prefix="/api/trend", tags=["trend"])


@router.get("/series")
def get_series(cycle: str = Query(default="MONTHLY"),
               limit: int = Query(default=12, ge=1, le=100),
               include_empty: bool = Query(default=False),
               _=Depends(require_login), db: Session = Depends(get_db)):
    """单周期趋势序列（图表数据源）"""
    return ok(data=TrendService.series(db, cycle, limit=limit, include_empty=include_empty))


@router.get("/all-cycles")
def get_all_cycles(limit: int = Query(default=12, ge=1, le=100),
                   _=Depends(require_login), db: Session = Depends(get_db)):
    """五周期各取最近 N 点（Dashboard 总览）"""
    return ok(data={"items": TrendService.all_cycles(db, limit=limit)})


@router.get("/timeline")
def get_timeline(cycle: Optional[str] = Query(default=None),
                 limit: int = Query(default=50, ge=1, le=200),
                 _=Depends(require_login), db: Session = Depends(get_db)):
    """报告时间轴：版本 × 指标摘要（按生成时间倒序）"""
    return ok(data=TrendService.timeline(db, cycle=cycle, limit=limit))
