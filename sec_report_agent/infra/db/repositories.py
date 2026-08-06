"""仓储层 — 各实体的数据访问封装（业务层不直接操作 ORM）"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from model.entity.entities import (
    DataSourceConfig, RawEvent, StdEvent, AssetVuln,
    ReportTask, ReportVersion, MetricSnapshot, AuditLog, PushLog,
    KnowledgeDoc, ReportConfig,
)
from model.enum.enums import TaskStatus, DataSourceType


# ═══════════ 数据源配置 ═══════════

class DataSourceConfigRepo:
    @staticmethod
    def list_all(db: Session, type_filter: Optional[str] = None) -> Sequence[DataSourceConfig]:
        stmt = select(DataSourceConfig)
        if type_filter:
            stmt = stmt.where(DataSourceConfig.type == type_filter)
        return db.execute(stmt.order_by(DataSourceConfig.id)).scalars().all()

    @staticmethod
    def get(db: Session, cfg_id: int) -> Optional[DataSourceConfig]:
        return db.get(DataSourceConfig, cfg_id)

    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[DataSourceConfig]:
        return db.execute(
            select(DataSourceConfig).where(DataSourceConfig.name == name)
        ).scalar_one_or_none()

    @staticmethod
    def get_enabled(db: Session, types: Optional[list[str]] = None) -> Sequence[DataSourceConfig]:
        stmt = select(DataSourceConfig).where(DataSourceConfig.status == "enabled")
        if types:
            stmt = stmt.where(DataSourceConfig.type.in_(types))
        return db.execute(stmt).scalars().all()

    @staticmethod
    def create(db: Session, **kwargs) -> DataSourceConfig:
        cfg = DataSourceConfig(**kwargs)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        return cfg

    @staticmethod
    def update(db: Session, cfg: DataSourceConfig, **kwargs) -> DataSourceConfig:
        for k, v in kwargs.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        db.commit()
        db.refresh(cfg)
        return cfg

    @staticmethod
    def toggle(db: Session, cfg: DataSourceConfig) -> DataSourceConfig:
        cfg.status = "disabled" if cfg.status == "enabled" else "enabled"
        db.commit()
        db.refresh(cfg)
        return cfg

    @staticmethod
    def delete(db: Session, cfg: DataSourceConfig):
        db.delete(cfg)
        db.commit()


# ═══════════ 原始/标准化事件 ═══════════

class RawEventRepo:
    @staticmethod
    def add_many(db: Session, events: list[dict]):
        if not events:
            return 0
        db.bulk_insert_mappings(RawEvent, events)
        db.commit()
        return len(events)

    @staticmethod
    def count_by_task(db: Session, task_id: int, status: Optional[str] = None) -> int:
        stmt = select(func.count(RawEvent.id)).where(RawEvent.task_id == task_id)
        if status:
            stmt = stmt.where(RawEvent.status == status)
        return db.execute(stmt).scalar() or 0


class StdEventRepo:
    @staticmethod
    def add_many(db: Session, events: list[dict]):
        if not events:
            return 0
        db.bulk_insert_mappings(StdEvent, events)
        db.commit()
        return len(events)

    @staticmethod
    def delete_by_task(db: Session, task_id: int):
        """重跑前清理旧数据（幂等重跑关键）"""
        stmt = StdEvent.__table__.delete().where(StdEvent.task_id == task_id)
        db.execute(stmt)
        db.commit()

    @staticmethod
    def list_by_task(db: Session, task_id: int, limit: int = 5000) -> Sequence[StdEvent]:
        return db.execute(
            select(StdEvent).where(StdEvent.task_id == task_id).limit(limit)
        ).scalars().all()

    @staticmethod
    def count_by_task(db: Session, task_id: int) -> int:
        return db.execute(
            select(func.count(StdEvent.id)).where(StdEvent.task_id == task_id)
        ).scalar() or 0


# ═══════════ 资产漏洞 ═══════════

class AssetVulnRepo:
    @staticmethod
    def list_all(db: Session, limit: int = 20000) -> Sequence[AssetVuln]:
        return db.execute(select(AssetVuln).limit(limit)).scalars().all()

    @staticmethod
    def clear(db: Session):
        db.execute(AssetVuln.__table__.delete())
        db.commit()

    @staticmethod
    def add_many(db: Session, items: list[dict]):
        if not items:
            return 0
        db.bulk_insert_mappings(AssetVuln, items)
        db.commit()
        return len(items)


# ═══════════ 报告任务 ═══════════

class ReportTaskRepo:
    @staticmethod
    def create(db: Session, **kwargs) -> ReportTask:
        task = ReportTask(**kwargs)
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def get(db: Session, task_id: int) -> Optional[ReportTask]:
        return db.get(ReportTask, task_id)

    @staticmethod
    def update(db: Session, task: ReportTask, **kwargs):
        for k, v in kwargs.items():
            setattr(task, k, v)
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def find_existing(db: Session, cycle: str, window_start: str, window_end: str) -> Optional[ReportTask]:
        """幂等：同周期同窗口已存在的任务（PENDING/RUNNING/SUCCESS 不重复建）"""
        return db.execute(
            select(ReportTask).where(
                ReportTask.cycle == cycle,
                ReportTask.window_start == window_start,
                ReportTask.window_end == window_end,
                ReportTask.status.in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value, TaskStatus.SUCCESS.value]),
            )
        ).scalars().first()

    @staticmethod
    def list_all(db: Session, cycle: Optional[str] = None, status: Optional[str] = None,
             keyword: Optional[str] = None, offset: int = 0, limit: int = 20) -> tuple[Sequence[ReportTask], int]:
        stmt = select(ReportTask)
        count_stmt = select(func.count(ReportTask.id))
        if cycle:
            stmt = stmt.where(ReportTask.cycle == cycle)
            count_stmt = count_stmt.where(ReportTask.cycle == cycle)
        if status:
            stmt = stmt.where(ReportTask.status == status)
            count_stmt = count_stmt.where(ReportTask.status == status)
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(or_(ReportTask.cycle.like(like), ReportTask.trace_id.like(like)))
            count_stmt = count_stmt.where(or_(ReportTask.cycle.like(like), ReportTask.trace_id.like(like)))
        total = db.execute(count_stmt).scalar() or 0
        rows = db.execute(
            stmt.order_by(ReportTask.id.desc()).offset(offset).limit(limit)
        ).scalars().all()
        return rows, total


# ═══════════ 报告版本 ═══════════

class ReportVersionRepo:
    @staticmethod
    def create(db: Session, **kwargs) -> ReportVersion:
        ver = ReportVersion(**kwargs)
        db.add(ver)
        db.commit()
        db.refresh(ver)
        return ver

    @staticmethod
    def get(db: Session, version_id: int) -> Optional[ReportVersion]:
        return db.get(ReportVersion, version_id)

    @staticmethod
    def list_by_task(db: Session, task_id: int) -> Sequence[ReportVersion]:
        return db.execute(
            select(ReportVersion).where(ReportVersion.task_id == task_id)
            .order_by(ReportVersion.version_no.desc())
        ).scalars().all()

    @staticmethod
    def get_latest_by_task(db: Session, task_id: int) -> Optional[ReportVersion]:
        return db.execute(
            select(ReportVersion).where(ReportVersion.task_id == task_id)
            .order_by(ReportVersion.id.desc()).limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def next_version_no(db: Session, task_id: int) -> int:
        cur = db.execute(
            select(func.max(ReportVersion.version_no)).where(ReportVersion.task_id == task_id)
        ).scalar()
        return (cur or 0) + 1

    @staticmethod
    def list_all(db: Session, cycle: Optional[str] = None, offset: int = 0, limit: int = 20,
             keyword: Optional[str] = None) -> tuple[Sequence[ReportVersion], int]:
        stmt = select(ReportVersion)
        count_stmt = select(func.count(ReportVersion.id))
        if cycle:
            stmt = stmt.where(ReportVersion.cycle == cycle)
            count_stmt = count_stmt.where(ReportVersion.cycle == cycle)
        if keyword:
            like = f"%{keyword}%"
            stmt = stmt.where(ReportVersion.title.like(like))
            count_stmt = count_stmt.where(ReportVersion.title.like(like))
        total = db.execute(count_stmt).scalar() or 0
        rows = db.execute(
            stmt.order_by(ReportVersion.id.desc()).offset(offset).limit(limit)
        ).scalars().all()
        return rows, total


# ═══════════ 指标快照 ═══════════

class MetricSnapshotRepo:
    @staticmethod
    def create(db: Session, **kwargs) -> MetricSnapshot:
        snap = MetricSnapshot(**kwargs)
        db.add(snap)
        db.commit()
        db.refresh(snap)
        return snap

    @staticmethod
    def get(db: Session, snap_id: int) -> Optional[MetricSnapshot]:
        return db.get(MetricSnapshot, snap_id)

    @staticmethod
    def get_by_task(db: Session, task_id: int) -> Optional[MetricSnapshot]:
        return db.execute(
            select(MetricSnapshot).where(MetricSnapshot.task_id == task_id)
            .order_by(MetricSnapshot.id.desc())
        ).scalars().first()

    @staticmethod
    def find_prev_snapshot(db: Session, cycle: str, window_start: str,
                           window_end: str) -> Optional[MetricSnapshot]:
        """同周期上一窗口快照：window_end < 当前 we 的最近一个（环比数据源）"""
        stmt = select(MetricSnapshot).where(
            MetricSnapshot.cycle == cycle,
            MetricSnapshot.window_end < window_end,
        ).order_by(MetricSnapshot.window_end.desc(), MetricSnapshot.id.desc())
        return db.execute(stmt).scalars().first()


# ═══════════ 审计日志 ═══════════

class AuditLogRepo:
    @staticmethod
    def add(db: Session, operator: str, action: str, target_type: str = "",
            target_id: int = 0, detail: str = "", client_ip: str = "", trace_id: str = "") -> AuditLog:
        log = AuditLog(
            operator=operator, action=action, target_type=target_type,
            target_id=target_id, detail=detail, client_ip=client_ip, trace_id=trace_id,
        )
        db.add(log)
        db.commit()
        return log

    @staticmethod
    def list_all(db: Session, target_type: Optional[str] = None, target_id: Optional[int] = None,
             limit: int = 100) -> Sequence[AuditLog]:
        stmt = select(AuditLog)
        if target_type:
            stmt = stmt.where(AuditLog.target_type == target_type)
        if target_id:
            stmt = stmt.where(AuditLog.target_id == target_id)
        return db.execute(stmt.order_by(AuditLog.id.desc()).limit(limit)).scalars().all()

    @staticmethod
    def list_by_target(db: Session, target_type: str, target_id: int,
                       limit: int = 100) -> Sequence[AuditLog]:
        """按目标对象查询审计记录"""
        return AuditLogRepo.list_all(db, target_type=target_type, target_id=target_id, limit=limit)


# ═══════════ 推送记录 ═══════════

class PushLogRepo:
    @staticmethod
    def create(db: Session, **kwargs) -> PushLog:
        log = PushLog(**kwargs)
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def list_by_version(db: Session, version_id: int) -> Sequence[PushLog]:
        return db.execute(
            select(PushLog).where(PushLog.version_id == version_id)
            .order_by(PushLog.id.desc())
        ).scalars().all()


# ═══════════ 知识库文档（V1.3） ═══════════

class KnowledgeDocRepo:
    @staticmethod
    def list_all(db: Session, category: Optional[str] = None) -> Sequence[KnowledgeDoc]:
        stmt = select(KnowledgeDoc)
        if category:
            stmt = stmt.where(KnowledgeDoc.category == category)
        return db.execute(stmt.order_by(KnowledgeDoc.id.desc())).scalars().all()

    @staticmethod
    def get(db: Session, doc_id: int) -> Optional[KnowledgeDoc]:
        return db.get(KnowledgeDoc, doc_id)

    @staticmethod
    def list_enabled(db: Session, limit: int = 20) -> Sequence[KnowledgeDoc]:
        """启用文档（研判注入源）"""
        return db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.enabled == "enabled")
            .order_by(KnowledgeDoc.id.desc()).limit(limit)
        ).scalars().all()

    @staticmethod
    def create(db: Session, **kwargs) -> KnowledgeDoc:
        doc = KnowledgeDoc(**kwargs)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def update(db: Session, doc: KnowledgeDoc, **kwargs) -> KnowledgeDoc:
        for k, v in kwargs.items():
            if hasattr(doc, k):
                setattr(doc, k, v)
        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def toggle(db: Session, doc: KnowledgeDoc) -> KnowledgeDoc:
        doc.enabled = "disabled" if doc.enabled == "enabled" else "enabled"
        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def delete(db: Session, doc: KnowledgeDoc):
        db.delete(doc)
        db.commit()


# ═══════════ 报告选配（V1.3，单例） ═══════════

class ReportConfigRepo:
    DEFAULT_SECTIONS = {
        "overview": True, "alert": True, "vuln": True,
        "attack": True, "trend": True, "suggestion": True,
    }
    DEFAULT_CYCLES = ["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"]

    @staticmethod
    def get_or_create(db: Session) -> ReportConfig:
        cfg = db.get(ReportConfig, 1)
        if not cfg:
            cfg = ReportConfig(
                id=1,
                enabled_cycles=ReportConfigRepo.DEFAULT_CYCLES,
                sections=dict(ReportConfigRepo.DEFAULT_SECTIONS),
                push_channels=["local"],
                auto_generate="disabled",
            )
            db.add(cfg)
            db.commit()
            db.refresh(cfg)
        return cfg

    @staticmethod
    def save(db: Session, cfg: ReportConfig, **kwargs) -> ReportConfig:
        for k, v in kwargs.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        db.commit()
        db.refresh(cfg)
        return cfg
