"""ORM 实体定义 — 9 张核心表（MySQL 落地；SQLite 兜底兼容）

约定：
- 时间字段统一 String(32) 存 ISO 字符串（跨库一致，免序列化）
- 大字段用 Text / JSON（SQLite 存 TEXT，MySQL 存原生 JSON）
"""

from datetime import datetime

from sqlalchemy import String, Text, Integer, Float, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from infra.db.base import Base


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DataSourceConfig(Base):
    """数据源配置"""
    __tablename__ = "data_source_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(16), index=True)          # DataSourceType
    status: Mapped[str] = mapped_column(String(8), default="enabled")  # enabled/disabled
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)      # 连接/路径配置
    filter_rules_json: Mapped[dict] = mapped_column(JSON, default=dict)  # 过滤/降噪规则
    sync_strategy: Mapped[str] = mapped_column(String(16), default="window")  # window/incremental
    description: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[str] = mapped_column(String(32), default=_now)
    updated_at: Mapped[str] = mapped_column(String(32), default=_now, onupdate=_now)


class RawEvent(Base):
    """原始数据落地（清洗前原样保留，异常数据 status=ERROR）"""
    __tablename__ = "raw_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(16), index=True)
    source_name: Mapped[str] = mapped_column(String(64), default="")
    receive_time: Mapped[str] = mapped_column(String(32), index=True)
    raw_content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(8), default="PENDING")  # PENDING/OK/ERROR
    error_msg: Mapped[str] = mapped_column(String(255), default="")
    task_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    trace_id: Mapped[str] = mapped_column(String(32), default="")


class StdEvent(Base):
    """标准化安全事件（指标计算输入）"""
    __tablename__ = "std_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_time: Mapped[str] = mapped_column(String(32), index=True)
    source_type: Mapped[str] = mapped_column(String(16), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    risk_level: Mapped[str] = mapped_column(String(8), index=True)
    asset_ip: Mapped[str] = mapped_column(String(64), default="")
    src_ip: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="")
    device_source: Mapped[str] = mapped_column(String(64), default="")
    raw_content: Mapped[str] = mapped_column(Text, default="")
    dedup_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    task_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


class AssetVuln(Base):
    """资产漏洞台账（DB 数据源）"""
    __tablename__ = "asset_vuln"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_ip: Mapped[str] = mapped_column(String(64), index=True)
    asset_name: Mapped[str] = mapped_column(String(128), default="")
    vuln_name: Mapped[str] = mapped_column(String(255), index=True)
    cvss: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(8), index=True)
    status: Mapped[str] = mapped_column(String(16), default="unfixed")  # unfixed/fixed/ignored
    discover_time: Mapped[str] = mapped_column(String(32), default="")
    fix_deadline: Mapped[str] = mapped_column(String(32), default="")
    fix_time: Mapped[str] = mapped_column(String(32), default="")
    source_name: Mapped[str] = mapped_column(String(64), default="")


class ReportTask(Base):
    """报告任务"""
    __tablename__ = "report_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle: Mapped[str] = mapped_column(String(16), index=True)         # ReportCycle
    window_start: Mapped[str] = mapped_column(String(32))
    window_end: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    trigger_type: Mapped[str] = mapped_column(String(16), default="MANUAL")
    trace_id: Mapped[str] = mapped_column(String(32), default="")
    error_msg: Mapped[str] = mapped_column(String(500), default="")
    data_source_stats: Mapped[dict] = mapped_column(JSON, default=dict)  # 各数据源拉取统计
    started_at: Mapped[str] = mapped_column(String(32), default="")
    finished_at: Mapped[str] = mapped_column(String(32), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(32), default=_now)
    updated_at: Mapped[str] = mapped_column(String(32), default=_now, onupdate=_now)


class ReportVersion(Base):
    """报告版本（备忘录模式：初稿快照）"""
    __tablename__ = "report_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    cycle: Mapped[str] = mapped_column(String(16), index=True)
    window_start: Mapped[str] = mapped_column(String(32))
    window_end: Mapped[str] = mapped_column(String(32))
    version_no: Mapped[int] = mapped_column(Integer, default=1)         # 版本号（task 内递增）
    version_type: Mapped[str] = mapped_column(String(16), default="AI_DRAFT")
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    title: Mapped[str] = mapped_column(String(255), default="")
    content_md: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(500), default="")     # 主文件（md 或 docx）
    metric_snapshot_id: Mapped[int] = mapped_column(Integer, default=0)  # 关联 MetricSnapshot
    operator: Mapped[str] = mapped_column(String(64), default="system")
    remark: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


class KnowledgeDoc(Base):
    """知识库文档（研判参考注入源，V1.3）"""
    __tablename__ = "knowledge_doc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(32), default="general", index=True)  # general/attack/defense/regulation
    content: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[str] = mapped_column(String(8), default="enabled")   # enabled/disabled
    created_at: Mapped[str] = mapped_column(String(32), default=_now)
    updated_at: Mapped[str] = mapped_column(String(32), default=_now, onupdate=_now)


class ReportConfig(Base):
    """报告选配（单例 id=1，V1.3）"""
    __tablename__ = "report_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled_cycles: Mapped[list] = mapped_column(JSON, default=list)      # 启用的报告周期
    sections: Mapped[dict] = mapped_column(JSON, default=dict)            # 章节开关 {overview: true, ...}
    push_channels: Mapped[list] = mapped_column(JSON, default=list)       # 推送渠道
    auto_generate: Mapped[str] = mapped_column(String(8), default="disabled")  # enabled/disabled
    updated_at: Mapped[str] = mapped_column(String(32), default=_now, onupdate=_now)


class MetricSnapshot(Base):
    """指标快照（溯源/对比/防幻觉）"""
    __tablename__ = "metric_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    cycle: Mapped[str] = mapped_column(String(16))
    window_start: Mapped[str] = mapped_column(String(32))
    window_end: Mapped[str] = mapped_column(String(32))
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)      # MetricSet.to_dict()
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


class AuditLog(Base):
    """操作审计日志"""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operator: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(32), index=True)         # 动作类型
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(String(500), default="")
    client_ip: Mapped[str] = mapped_column(String(64), default="")
    trace_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


class PushLog(Base):
    """推送记录"""
    __tablename__ = "push_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(Integer, index=True)
    channel: Mapped[str] = mapped_column(String(32), default="local")   # local/email/dingtalk/wecom
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[str] = mapped_column(String(32), default=_now)
