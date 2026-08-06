"""报告 Prompt 工厂 — 构建 LLM 研判提示词 + LLM 失败降级模板

防幻觉原则：LLM 只做"解读与撰写"，所有数字来自 MetricSet 事实，Prompt 中明确禁止编造。
"""

import json
from typing import Optional

from model.struct.structs import MetricSet
from common.constant.constant import SECTION_TITLES, REPORT_SECTIONS

SYSTEM_PROMPT = """你是企业网络安全态势报告撰写专家，负责基于结构化指标数据撰写专业、客观的周期安全态势报告。

严格遵守以下规则：
1. 所有数据、数字必须严格来自提供的指标 JSON，禁止编造任何统计数字。
2. 数据不足时明确写"数据不足"，不要推测填充。
3. 语言专业、简洁、分点清晰，符合企业安全运营报告口径。
4. 输出 JSON 格式：{"sections": {"overview": "...", "alert": "...", "vuln": "...", "attack": "...", "trend": "...", "suggestion": "..."}, "risk_level": "HIGH|MEDIUM|LOW"}
5. sections 中每个章节为一段 markdown 文本（可含小标题与列表），不要输出 JSON 之外的任何内容。"""


def build_report_messages(metric: MetricSet, risk_flags: list, rag_refs: list,
                          max_chars: Optional[int] = None) -> list[dict]:
    """构建研判 Prompt 消息列表"""
    from config.settings import settings
    limit = max_chars or settings.llm_max_input_chars

    metric_json = json.dumps(metric.to_dict(), ensure_ascii=False, indent=2)
    if len(metric_json) > limit:
        metric_json = metric_json[:limit] + "\n...(截断)"

    flag_lines = "\n".join(
        f"- [{f.level}] {f.message}" for f in (risk_flags or [])
    ) or "- 无规则命中"

    ref_lines = "\n".join(
        f"- [{r.get('kb_label', '知识库')}] {r.get('content', '')[:200]}"
        for r in (rag_refs or [])[:5]
    ) or "- 无知识库引用"

    user_content = f"""请根据以下周期安全指标数据撰写网络安全态势报告。

【统计周期】
{metric.cycle}  {metric.window_start} ~ {metric.window_end}

【规则引擎风险标记】
{flag_lines}

【知识库参考（可选）】
{ref_lines}

【结构化指标数据】
```json
{metric_json}
```

【章节要求】
{chr(10).join(f"{title}: 围绕对应指标展开，包含关键数据与结论" for title in SECTION_TITLES.values())}

请输出符合 system 要求的 JSON。"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def parse_llm_response(content: str) -> dict:
    """解析 LLM 返回的 JSON（容忍代码块包裹/前后噪声）"""
    text = (content or "").strip()
    # 去掉 ```json ... ``` 包裹
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 提取第一个 { ... } 块
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def _fmt_dict(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in (d or {}).items())


def _fmt_top(items: list) -> str:
    if not items:
        return "暂无数据"
    parts = []
    for i in items[:5]:
        name = i.get("ip") or i.get("type") or i.get("asset") or i.get("asset_ip") or "unknown"
        parts.append(f"{name}({i.get('count', 0)})")
    return "; ".join(parts)


def build_fallback_sections(metric: MetricSet, risk_flags: list) -> dict:
    """LLM 失败降级模板 — 基于指标事实生成确定性章节文本（不调用 LLM）"""
    alert = metric.alert or {}
    vuln = metric.vuln or {}
    top = metric.top or {}
    trend = metric.trend or {}

    high = alert.get("high", 0)
    total = alert.get("total", 0)
    close_rate = alert.get("close_rate", 0)
    unfixed_high = vuln.get("unfixed_high", 0)
    top_src = top.get("top_src") or []
    compare = trend.get("compare") or None

    risk_lines = "\n".join(f"- {f.message}" for f in (risk_flags or [])) or "- 无规则命中"

    sections = {
        "overview": (
            f"本周期（{metric.window_start} 至 {metric.window_end}）共监测到安全事件 {total} 起，"
            f"其中高危 {high} 起，事件闭环率 {close_rate:.1%}。整体安全态势需持续关注。\n\n"
            f"规则引擎风险标记：\n{risk_lines}"
        ),
        "alert": (
            f"告警总量 {total} 起，高危 {high} 起。\n"
            f"- 事件类型分布：{_fmt_dict(alert.get('by_type', {}))}\n"
            f"- 闭环率：{close_rate:.1%}\n"
            f"- 按天分布：{len(trend.get('by_day', []))} 天有事件记录"
        ),
        "vuln": (
            f"漏洞台账共 {vuln.get('total', 0)} 条，未修复 {vuln.get('unfixed', 0)} 条，"
            f"其中未修复高危 {unfixed_high} 条，漏洞闭环率 {vuln.get('close_rate', 0):.1%}。\n"
            f"未修复 TOP 资产：{_fmt_top(vuln.get('top_assets', []))}"
        ),
        "attack": (
            f"TOP 攻击源：{_fmt_top(top_src)}\n"
            f"TOP 攻击类型：{_fmt_top(top.get('top_type', []))}\n"
            f"TOP 受害资产：{_fmt_top(top.get('top_asset', []))}"
        ),
        "trend": (
            f"事件按天分布共 {len(trend.get('by_day', []))} 天，"
            f"日均 {round(total / max(len(trend.get('by_day', []) or [1]), 1), 1)} 起。"
            + (f"环比上期：告警总量 {compare.get('alert_total', {}).get('delta', '暂无')}。"
               if compare else "环比/同比数据暂缺，建议结合历史报告对比。")
        ),
        "suggestion": (
            "1. 优先处置高危告警与未修复高危漏洞，明确责任人与时限；\n"
            "2. 对 TOP 攻击源实施封禁与威胁情报联动；\n"
            "3. 提升事件闭环效率，优化处置流程与自动化响应；\n"
            "4. 加强重点资产（TOP 受害资产）防护与监控覆盖。"
        ),
    }
    return sections
