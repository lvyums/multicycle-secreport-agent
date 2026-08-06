"""业务常量 — 报告标题模板 / 空报告文案 / 默认章节（不涉及配置项，配置走 settings）"""


# ── 报告标题模板 ──
TITLE_TEMPLATE = "{cycle_label}网络安全态势报告（{window_start} 至 {window_end}）"

# ── 空报告文案 ──
EMPTY_REPORT_TITLE = "{cycle_label}网络安全态势报告（{window_start} 至 {window_end}）"
EMPTY_REPORT_BODY = (
    "## 一、总体态势\n\n"
    "本周期内未采集到有效安全事件数据，报告为空报告。\n\n"
    "可能原因：\n"
    "1. 数据源未接入或已禁用；\n"
    "2. 采集窗口内确实无安全事件；\n"
    "3. 清洗链路将所有事件判定为噪声丢弃。\n\n"
    "建议：检查数据源配置与日志采集状态，确认无漏采。\n"
)

# ── 报告章节（非空报告固定骨架，正文由 LLM 填充）──
REPORT_SECTIONS = [
    "overview",       # 一、总体态势
    "alert",          # 二、告警分析
    "vuln",           # 三、漏洞与资产风险
    "attack",         # 四、攻击行为研判
    "trend",          # 五、趋势与预测
    "suggestion",     # 六、安全建议
]

SECTION_TITLES = {
    "overview": "一、总体态势",
    "alert": "二、告警分析",
    "vuln": "三、漏洞与资产风险",
    "attack": "四、攻击行为研判",
    "trend": "五、趋势与预测",
    "suggestion": "六、安全建议",
}

# ── 规则引擎默认风险标记前缀 ──
RISK_FLAG_PREFIX = "RISK"
