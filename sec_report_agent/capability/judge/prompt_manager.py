"""全局 Prompt 模板管理 — 含日志解析、实训评分等场景的 LLM 提示词"""

from typing import Optional

# 全局 System Prompt
GLOBAL_SYSTEM_PROMPT = """你是一个专业的日志安全分析助手，请严格遵循以下规则：
1. 基于知识库内容回答，不要编造信息
2. 输出结构化、分点、可直接落地的内容
3. 保持客观，不确定的内容标注"暂无依据"
4. 涉及安全风险时明确标注危害等级"""

# 模块级 System Prompt
MODULE_PROMPTS = {
    "default": "请基于提供的信息给出准确、专业的回答。",
    "log_parse": "你是一个日志解析专家。请识别日志类型，提取关键字段，并给出行为研判。",
}

# ═══════════════════════════════════════════════════
# LLM 降级专用 Prompt
# ═══════════════════════════════════════════════════

# 日志识别降级 Prompt
LOG_IDENTIFY_FALLBACK_PROMPT = """你是一个日志分析专家。以下是一条未能通过规则匹配识别的原始日志。
请分析它并返回 JSON 格式的识别结果（不要包含任何其他文字）：

{{
    "device_type": "识别到的设备类型（如 firewall/waf/ids/ips/ssh/web/server/db），
                    如果完全无法识别则返回 'unknown'",
    "confidence": 置信度 0-100 的整数,
    "identify_reason": "识别依据的简要说明"
}}

日志内容：
```
{log_line}
```
"""

# 日志解析降级 Prompt
LOG_PARSE_FALLBACK_PROMPT = """你是一个日志解析专家。以下是一条原始日志，规则引擎无法自动解析。
请提取其中的关键字段，返回 JSON 格式的解析结果（不要包含任何其他文字）：

{{
    "timestamp": "时间戳（如无法提取则返回 null）",
    "src_ip": "源 IP 地址",
    "dst_ip": "目的 IP 地址",
    "src_port": "源端口",
    "dst_port": "目的端口",
    "user": "用户名",
    "url": "URL 路径",
    "method": "HTTP 方法",
    "command": "执行的命令",
    "status": "状态/结果（如 failed/success/deny 等）",
    "device_type": "设备类型",
    "raw_log": "原始日志（截取前500字符）"
}}

如果某个字段不存在，设置为 null。尽最大努力提取信息。

日志内容：
```
{log_line}
```
"""

# 实训评分降级 Prompt
TRAINING_SCORING_PROMPT = """你是一个安全实训评分助理。请比较学员答案与标准答案的语义相似度。

标准答案：
{standard}

学员答案：
{submission}

请从以下两个维度评分：

1. content_match (0-100): 内容语义匹配度 — 学员答案是否表达了与标准答案相同的意思，
   关注"意图和关键信息"是否一致，而非文字是否逐字相同。

2. completeness (0-100): 完整性 — 学员答案是否覆盖了标准答案中的关键要点。

请以 JSON 格式返回（不要包含任何其他文字）：
{{
    "content_match": 分数,
    "completeness": 分数,
    "overall_score": 取 content_match 和 completeness 的加权平均 (content_match*0.6 + completeness*0.4),
    "feedback": "简要的评估反馈，指出优点和不足",
    "matched_key_concepts": ["学员答对的关键概念列表"],
    "missed_key_concepts": ["学员遗漏的关键概念列表"]
}}
"""

# 指导手册生成 Prompt
GUIDE_GENERATE_PROMPT = """你是一位资深安全架构师，请根据以下结构化数据生成一份详细的日志采集与分析指导手册。

## 基本信息
- 企业规模：{scale}
- 安全设备类型：{device_types}
- 设备数量：{device_count} 台
- 日均日志量：{daily_log_volume}
- 预算水平：{budget}
- 运维能力：{team_skill}

## 采集方案数据
以下是每种设备类型的采集方案（来自系统自动生成）：
```json
{collect_plans_json}
```

## 架构推荐数据
以下是系统推荐的架构方案：
```json
{architecture_json}
```

## 平台选型数据
以下是系统推荐的日志平台：
```json
{platform_json}
```

## 输出要求
请基于上述结构化数据，生成一份完整的 Markdown 格式指导手册。不要编造配置代码，直接引用采集方案中的 config_template。

请按以下章节组织内容：

# 日志采集与分析指导手册

## 1. 项目概述
基于基本信息，描述项目背景、建设目标、预期收益。

## 2. 架构方案
基于架构推荐数据，描述推荐架构、组件清单、数据流向、估算成本。

## 3. 设备采集配置
基于采集方案数据，为每种设备类型提供：
- 采集协议
- 配置代码（直接引用 config_template）
- 实施步骤
- 注意事项

## 4. 平台配置
基于平台选型数据，描述平台选择理由、部署配置要点。

## 5. 实施步骤
基于上述数据，制定分阶段实施计划。

## 6. 合规要求
等保 2.0 要求对照、日志留存策略、传输加密要求。

## 7. 运维手册
日常巡检清单、常见故障排查、性能优化建议。

## 8. 培训材料
团队培训要点、操作手册要点、考核标准。

请确保内容专业、基于数据、可直接落地执行。
"""


class PromptManager:
    """全局 Prompt 模板管理"""

    _version = "1.0.0"

    @classmethod
    def get_system_prompt(cls, module: str = "default") -> str:
        """获取模块 System Prompt，注入全局约束"""
        module_prompt = MODULE_PROMPTS.get(module, MODULE_PROMPTS["default"])
        return f"{GLOBAL_SYSTEM_PROMPT}\n\n{module_prompt}"

    @classmethod
    def build_messages(cls, module: str, user_input: str,
                       context: Optional[dict] = None,
                       system_override: Optional[str] = None) -> list[dict]:
        """组装完整消息列表（system + 用户输入 + 上下文）"""
        system_content = system_override or cls.get_system_prompt(module)
        messages = [
            {"role": "system", "content": system_content},
        ]
        if context and "rag_context" in context:
            messages.append({
                "role": "system",
                "content": f"知识库参考信息：\n{context['rag_context']}",
            })
        messages.append({"role": "user", "content": user_input})
        return messages

    @classmethod
    def get_prompt(cls, name: str, **kwargs) -> str:
        """获取指定名称的 prompt 模板，并格式化"""
        prompts = {
            "log_identify_fallback": LOG_IDENTIFY_FALLBACK_PROMPT,
            "log_parse_fallback": LOG_PARSE_FALLBACK_PROMPT,
            "training_scoring": TRAINING_SCORING_PROMPT,
            "guide_generate": GUIDE_GENERATE_PROMPT,
        }
        template = prompts.get(name)
        if not template:
            raise ValueError(f"未知 prompt 模板: {name}")
        return template.format(**kwargs)

    @classmethod
    def get_version(cls) -> str:
        """返回当前 Prompt 模板版本号"""
        return cls._version