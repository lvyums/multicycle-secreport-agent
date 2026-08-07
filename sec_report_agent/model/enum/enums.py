"""全局枚举 — 周期/任务状态/报告状态/数据源类型/风险等级/版本类型"""

from enum import Enum


class ReportCycle(str, Enum):
    """报告周期"""
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"

    @property
    def label(self) -> str:
        return {
            "DAILY": "日报",
            "WEEKLY": "周报",
            "MONTHLY": "月报",
            "QUARTERLY": "季报",
            "YEARLY": "年报",
        }[self.value]


class TaskStatus(str, Enum):
    """报告任务状态"""
    PENDING = "PENDING"      # 待执行
    RUNNING = "RUNNING"      # 执行中
    SUCCESS = "SUCCESS"      # 成功
    EMPTY = "EMPTY"          # 窗口内无数据（空报告）
    FAILED = "FAILED"        # 失败
    PARTIAL = "PARTIAL"      # 部分成功（部分数据源失败）

    @property
    def label(self) -> str:
        return {
            "PENDING": "待执行",
            "RUNNING": "执行中",
            "SUCCESS": "成功",
            "EMPTY": "无数据",
            "FAILED": "失败",
            "PARTIAL": "部分成功",
        }[self.value]


class ReportStatus(str, Enum):
    """报告版本状态"""
    DRAFT = "DRAFT"              # AI 初稿
    REVIEWING = "REVIEWING"      # 审核中
    APPROVED = "APPROVED"        # 终审通过
    ARCHIVED = "ARCHIVED"        # 已归档
    FAILED = "FAILED"            # 生成失败

    @property
    def label(self) -> str:
        return {
            "DRAFT": "初稿",
            "REVIEWING": "审核中",
            "APPROVED": "终审",
            "ARCHIVED": "已归档",
            "FAILED": "失败",
        }[self.value]


class DataSourceType(str, Enum):
    """数据源类型"""
    SYSLOG = "SYSLOG"        # Syslog 日志流
    API = "API"              # 告警平台 REST
    ES = "ES"                # Elasticsearch 日志检索（V2.5）
    DB = "DB"                # 资产/漏洞台账
    EXCEL = "EXCEL"          # Excel 导入（V1.2）
    INTEL = "INTEL"          # 外部威胁情报（V1.2）
    HISTORY = "HISTORY"      # 历史报告（V1.2）
    POLICY = "POLICY"        # 策略配置（V1.2）

    @property
    def label(self) -> str:
        return {
            "SYSLOG": "Syslog日志",
            "API": "告警平台",
            "ES": "ES日志检索",
            "DB": "资产台账",
            "EXCEL": "Excel导入",
            "INTEL": "威胁情报",
            "HISTORY": "历史报告",
            "POLICY": "策略配置",
        }[self.value]


class RiskLevel(str, Enum):
    """风险等级"""
    HIGH = "HIGH"        # 高危
    MEDIUM = "MEDIUM"    # 中危
    LOW = "LOW"          # 低危
    INFO = "INFO"        # 提示

    @property
    def label(self) -> str:
        return {
            "HIGH": "高危",
            "MEDIUM": "中危",
            "LOW": "低危",
            "INFO": "提示",
        }[self.value]


class VersionType(str, Enum):
    """报告版本类型"""
    AI_DRAFT = "AI_DRAFT"        # AI 初稿
    HUMAN_EDIT = "HUMAN_EDIT"    # 人工编辑
    FINAL = "FINAL"              # 终版

    @property
    def label(self) -> str:
        return {
            "AI_DRAFT": "AI初稿",
            "HUMAN_EDIT": "人工编辑",
            "FINAL": "终版",
        }[self.value]


class TriggerType(str, Enum):
    """任务触发方式"""
    MANUAL = "MANUAL"        # 手动触发
    SCHEDULE = "SCHEDULE"    # 定时调度
    RERUN = "RERUN"          # 重跑/补录

    @property
    def label(self) -> str:
        return {
            "MANUAL": "手动",
            "SCHEDULE": "定时",
            "RERUN": "重跑",
        }[self.value]
