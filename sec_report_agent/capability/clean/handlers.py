"""清洗责任链处理器 — 校验 / 去重降噪 / 归一化 / 分级 / 时间切片

每个 handler 独立职责，通过 CleanChain 串联；handle 返回 None 表示丢弃。
"""

import hashlib
from typing import Optional

from capability.clean.data_chain import CleanHandler, CleanContext, CleanChain
from model.struct.structs import StdEvent
from model.enum.enums import RiskLevel


class ValidateHandler(CleanHandler):
    """环节1：字段校验 — 缺关键字段丢弃"""

    name = "validate"

    def handle(self, event: StdEvent, ctx: CleanContext) -> Optional[StdEvent]:
        if not event.event_time or not event.event_type or not event.source_type:
            return None
        if len(event.event_time) < 10:
            return None
        return event


class DedupHandler(CleanHandler):
    """环节2：去重降噪 — 同源同类型同分钟指纹去重；INFO 噪声丢弃"""

    name = "dedup"

    def __init__(self, noise_types: Optional[list[str]] = None):
        # 降噪：INFO 级 policy 类事件直接丢弃（低价值）
        self._noise_types = noise_types or []
        self._seen: set[str] = set()

    def handle(self, event: StdEvent, ctx: CleanContext) -> Optional[StdEvent]:
        # 降噪
        if event.risk_level == RiskLevel.INFO.value and event.event_type in self._noise_types:
            return None
        if event.risk_level == RiskLevel.INFO.value and event.event_type == "policy":
            return None

        # 去重指纹：类型+来源+资产+分钟
        minute = event.event_time[:16] if len(event.event_time) >= 16 else event.event_time
        key = hashlib.md5(
            f"{event.event_type}|{event.src_ip}|{event.asset_ip}|{minute}".encode()
        ).hexdigest()
        if key in self._seen:
            return None
        self._seen.add(key)
        event.dedup_key = key
        return event


class NormalizeHandler(CleanHandler):
    """环节3：归一化 — extra 字段映射到 StdEvent 标准字段"""

    name = "normalize"

    def handle(self, event: StdEvent, ctx: CleanContext) -> Optional[StdEvent]:
        extra = event.extra or {}
        if not event.asset_ip:
            event.asset_ip = extra.get("asset_ip") or ""
        if not event.src_ip:
            event.src_ip = extra.get("src_ip") or ""
        if not event.risk_level or event.risk_level not in [r.value for r in RiskLevel]:
            hint = str(extra.get("risk_hint") or "LOW").upper()
            event.risk_level = hint if hint in [r.value for r in RiskLevel] else RiskLevel.LOW.value
        if not event.device_source:
            event.device_source = extra.get("device") or extra.get("source_name") or ""
        # 原始内容摘要截断（存库体积控制）
        if len(event.raw_content) > 500:
            event.raw_content = event.raw_content[:500] + "..."
        return event


class GradeHandler(CleanHandler):
    """环节4：分级修正 — 基于事件类型/来源进行专家级修正"""

    name = "grade"

    # 事件类型 → 最低风险兜底
    TYPE_MIN_RISK = {
        "brute_force": RiskLevel.MEDIUM.value,
        "lateral": RiskLevel.HIGH.value,
        "malware": RiskLevel.HIGH.value,
        "web_attack": RiskLevel.MEDIUM.value,
    }

    def handle(self, event: StdEvent, ctx: CleanContext) -> Optional[StdEvent]:
        min_risk = self.TYPE_MIN_RISK.get(event.event_type)
        if min_risk:
            order = {RiskLevel.INFO.value: 0, RiskLevel.LOW.value: 1,
                     RiskLevel.MEDIUM.value: 2, RiskLevel.HIGH.value: 3}
            if order.get(event.risk_level, 0) < order[min_risk]:
                event.risk_level = min_risk
        # 漏洞台账：unfixed 且高危保持，fixed 降为 INFO（不参与告警统计）
        if event.event_type == "vuln":
            status = (event.extra or {}).get("vuln_status") or ""
            if status == "fixed":
                event.risk_level = RiskLevel.INFO.value
            event.status = status
        return event


class SliceHandler(CleanHandler):
    """环节5：时间切片 — 校验窗口内 + 时间规整（分钟粒度）"""

    name = "slice"

    def handle(self, event: StdEvent, ctx: CleanContext) -> Optional[StdEvent]:
        if ctx.window_start and event.event_time < ctx.window_start:
            return None
        if ctx.window_end and event.event_time > ctx.window_end:
            return None
        # 规整到分钟（秒清零，聚合稳定性）
        if len(event.event_time) >= 19:
            event.event_time = event.event_time[:16] + ":00"
        return event


def build_default_chain() -> CleanChain:
    """构建默认清洗链（五环节）"""
    return CleanChain([
        ValidateHandler(),
        DedupHandler(noise_types=["policy"]),
        NormalizeHandler(),
        GradeHandler(),
        SliceHandler(),
    ])
