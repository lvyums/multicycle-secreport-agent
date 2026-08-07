"""应用指标（V2.3）— 进程内原子计数，/metrics 输出 Prometheus 文本格式，零新依赖

埋点：任务状态机 / LLM 调用 / 推送发送 / HTTP 请求（middleware）
输出：GET /metrics → text/plain; version=0.0.4（Prometheus 拉取标准）
"""

import threading

_lock = threading.Lock()

# 计数器：{名称: 计数}
_COUNTERS: dict[str, int] = {}

# 标签化计数：{名称: {标签值: 计数}}
_LABELED: dict[str, dict[str, int]] = {}

_METADATA: dict[str, str] = {
    "sec_report_task_total": "报告任务终态计数（status=DONE/EMPTY/FAILED/PARTIAL）",
    "sec_report_task_duration_seconds_total": "任务耗时累计秒（cycle 标签）",
    "sec_report_llm_calls_total": "LLM 调用计数（mode=llm/fallback，result=success/fail）",
    "sec_report_push_total": "推送发送计数（channel 标签，result=success/fail）",
    "sec_report_http_requests_total": "HTTP 请求计数（method 标签）",
}


def inc(name: str, labels: dict | None = None, value: int = 1):
    """原子计数。无标签走简单计数器；有标签走标签化计数（labels 全部 str 值）"""
    with _lock:
        if not labels:
            _COUNTERS[name] = _COUNTERS.get(name, 0) + value
            return
        key = "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
        bucket = _LABELED.setdefault(name, {})
        bucket[key] = bucket.get(key, 0) + value


def _fmt_metric(name: str, labels: dict | None, value: int, help_text: str) -> str:
    if labels is None:
        return f"{name} {value}"
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{label_str}}} {value}"


def reset_for_test(metric_name: str):
    """测试专用：清零指定计数器（含标签化）"""
    with _lock:
        _COUNTERS.pop(metric_name, None)
        _LABELED.pop(metric_name, None)


def render() -> str:
    """渲染 Prometheus 文本格式（含 # HELP / # TYPE counter）"""
    lines: list[str] = []
    all_names = sorted(set(_COUNTERS) | set(_LABELED) | set(_METADATA))
    for name in all_names:
        help_text = _METADATA.get(name, name)
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} counter")
        if name in _COUNTERS:
            lines.append(_fmt_metric(name, None, _COUNTERS[name], help_text))
        for key, val in sorted(_LABELED.get(name, {}).items()):
            labels = dict(pair.split("=", 1) for pair in key.split("|"))
            lines.append(_fmt_metric(name, labels, val, help_text))
    return "\n".join(lines) + "\n"


def snapshot() -> dict:
    """供测试/调试读取的原始快照"""
    with _lock:
        return {"counters": dict(_COUNTERS), "labeled": {k: dict(v) for k, v in _LABELED.items()}}
