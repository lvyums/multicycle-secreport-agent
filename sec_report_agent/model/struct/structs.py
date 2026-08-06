"""核心数据模型 — 数据流贯穿各层的数据结构

数据流：RawEvent → StdEvent → MetricSet → JudgeResult → RenderData
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StdEvent:
    """标准化安全事件（清洗后的统一结构）"""
    event_time: str                 # 事件时间 ISO 字符串
    source_type: str                # 数据源类型（SYSLOG/API/DB）
    event_type: str                 # 事件类型（brute_force/web_attack/...）
    risk_level: str                 # HIGH/MEDIUM/LOW/INFO
    asset_ip: str = ""              # 资产 IP
    src_ip: str = ""                # 来源 IP
    status: str = ""                # 事件状态（open/closed）
    device_source: str = ""         # 设备来源
    raw_content: str = ""           # 原始内容摘要
    dedup_key: str = ""             # 去重指纹
    extra: dict = field(default_factory=dict)  # 扩展字段

    def to_dict(self) -> dict:
        return {
            "event_time": self.event_time,
            "source_type": self.source_type,
            "event_type": self.event_type,
            "risk_level": self.risk_level,
            "asset_ip": self.asset_ip,
            "src_ip": self.src_ip,
            "status": self.status,
            "device_source": self.device_source,
            "raw_content": self.raw_content,
            "dedup_key": self.dedup_key,
            "extra": self.extra,
        }


@dataclass
class MetricSet:
    """指标集合 — 报告数据的事实来源（防幻觉核心：LLM 只解读、不计算）"""
    cycle: str = ""                        # 周期
    window_start: str = ""                 # 窗口开始
    window_end: str = ""                   # 窗口结束
    alert: dict = field(default_factory=dict)      # 告警指标
    vuln: dict = field(default_factory=dict)       # 漏洞指标
    top: dict = field(default_factory=dict)        # TOP 排行
    trend: dict = field(default_factory=dict)      # 趋势（环比/同比）
    raw: dict = field(default_factory=dict)        # 原始统计快照

    def to_dict(self) -> dict:
        return {
            "cycle": self.cycle,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "alert": self.alert,
            "vuln": self.vuln,
            "top": self.top,
            "trend": self.trend,
            "raw": self.raw,
        }


@dataclass
class JudgeResult:
    """双路研判结果"""
    risk_flags: list = field(default_factory=list)      # 规则引擎风险标记
    risk_level: str = "LOW"                              # 综合风险等级
    sections: dict = field(default_factory=dict)         # LLM 生成的各章节文本
    llm_ok: bool = False                                 # LLM 是否成功
    llm_error: str = ""                                  # LLM 失败原因
    rag_refs: list = field(default_factory=list)         # RAG 召回引用

    def to_dict(self) -> dict:
        return {
            "risk_flags": self.risk_flags,
            "risk_level": self.risk_level,
            "sections": self.sections,
            "llm_ok": self.llm_ok,
            "llm_error": self.llm_error,
            "rag_refs": self.rag_refs,
        }


@dataclass
class RenderData:
    """渲染数据 — 模板填充的最终数据源"""
    cycle: str = ""
    cycle_label: str = ""
    window_start: str = ""
    window_end: str = ""
    generated_at: str = ""
    metric: dict = field(default_factory=dict)     # 结构化指标（直接来自 MetricSet）
    judge: dict = field(default_factory=dict)      # 研判文本/标记
    empty: bool = False                            # 是否空报告
    extra: dict = field(default_factory=dict)      # 扩展（如生成耗时/数据源统计）

    def to_dict(self) -> dict:
        return {
            "cycle": self.cycle,
            "cycle_label": self.cycle_label,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "generated_at": self.generated_at,
            "metric": self.metric,
            "judge": self.judge,
            "empty": self.empty,
            "extra": self.extra,
        }
