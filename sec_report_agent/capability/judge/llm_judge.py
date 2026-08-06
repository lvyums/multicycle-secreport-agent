"""LLM 研判器 — 双路研判的第二路（规则引擎第一路）

职责：输入指标事实 MetricSet + 规则风险标记 → 生成各章节报告文本
降级策略：LLM 失败/超时/无 Key → 自动使用确定性降级模板（业务不中断）
"""

import json
from typing import Optional

from config.settings import settings
from common.logger.logger import LogManager
from model.struct.structs import MetricSet, JudgeResult
from capability.judge.prompt_builder import (
    build_report_messages, parse_llm_response, build_fallback_sections,
)

logger = LogManager.get_logger()


class LLMJudge:
    """LLM 研判器"""

    def __init__(self, llm=None):
        self._llm = llm  # 延迟获取（避免无 Key 环境 import 报错）

    def _get_llm(self):
        if self._llm is None:
            from capability.judge.llm_factory import LLMFactory
            self._llm = LLMFactory.create("main")
        return self._llm

    async def judge(self, metric: MetricSet, risk_flags: list,
                    rag_refs: Optional[list] = None) -> JudgeResult:
        """执行研判：LLM 生成章节文本，失败降级"""
        result = JudgeResult(
            risk_flags=[f.to_dict() for f in (risk_flags or [])],
            rag_refs=rag_refs or [],
        )

        # 无 API Key → 直接降级（不尝试网络调用）
        if not settings.llm_api_key or not settings.llm_fallback_enabled:
            result.sections = build_fallback_sections(metric, risk_flags or [])
            result.llm_ok = False
            result.llm_error = "未配置 LLM API Key"
            result.risk_level = self._composite(risk_flags or [])
            return result

        try:
            messages = build_report_messages(metric, risk_flags or [], rag_refs or [])
            llm = self._get_llm()
            resp = await llm.chat(messages, temperature=settings.llm_temperature)
            if not resp.get("success"):
                raise RuntimeError(resp.get("error") or "LLM 调用失败")

            parsed = parse_llm_response(resp.get("content") or "")
            sections = parsed.get("sections") or {}
            if not sections:
                raise RuntimeError("LLM 返回缺少 sections 字段")

            result.sections = sections
            result.risk_level = parsed.get("risk_level") or self._composite(risk_flags or [])
            result.llm_ok = True
            logger.info(f"[JUDGE] LLM 研判成功，章节数={len(sections)}")
        except Exception as e:
            logger.warning(f"[JUDGE] LLM 研判失败，降级模板: {e}")
            result.sections = build_fallback_sections(metric, risk_flags or [])
            result.llm_ok = False
            result.llm_error = str(e)
            result.risk_level = self._composite(risk_flags or [])

        return result

    @staticmethod
    def _composite(flags: list) -> str:
        """综合风险等级（与规则引擎一致：取最高）"""
        order = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
        if not flags:
            return "LOW"
        return max((f.level for f in flags), key=lambda x: order.get(x, 0))
