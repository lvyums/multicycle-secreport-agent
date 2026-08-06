"""Mock 数据生成器 — 确定性生成三类数据源原始数据（seed 固定，结果可复现）

输出：
- Syslog 日志行（RFC3164 简化格式）→ data/mock/syslog.log
- API 告警 JSON 行 → data/mock/api_alerts.jsonl
- DB 漏洞台账 CSV → data/mock/vulns.csv
"""

import csv
import json
import os
import random
from datetime import datetime, timedelta

from common.logger.logger import LogManager

logger = LogManager.get_logger()

MOCK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "mock")

# ── 事件类型池 ──
EVENT_TYPES = [
    {"type": "brute_force", "label": "暴力破解", "weight": 30, "risk": ["HIGH", "MEDIUM"]},
    {"type": "web_attack", "label": "Web攻击", "weight": 25, "risk": ["HIGH", "MEDIUM", "LOW"]},
    {"type": "malware", "label": "恶意软件", "weight": 12, "risk": ["HIGH", "MEDIUM"]},
    {"type": "dos", "label": "拒绝服务", "weight": 10, "risk": ["MEDIUM", "LOW"]},
    {"type": "phishing", "label": "钓鱼邮件", "weight": 8, "risk": ["MEDIUM", "LOW"]},
    {"type": "lateral", "label": "横向移动", "weight": 8, "risk": ["HIGH", "MEDIUM"]},
    {"type": "policy", "label": "违规操作", "weight": 7, "risk": ["LOW", "INFO"]},
]

# ── IP 池 ──
SRC_IPS = ["203.0.113.{}".format(i) for i in range(1, 21)]          # 攻击源
ASSET_IPS = ["10.0.{}.{}".format(seg, host) for seg in range(1, 3) for host in range(1, 6)]  # 内网资产
DEVICES = ["fw-gw", "ids-01", "waf-01", "db-firewall", "mail-gw", "core-sw"]

RISK_WEIGHTS = {"HIGH": 15, "MEDIUM": 30, "LOW": 40, "INFO": 15}


def _pick_event_type(rng: random.Random) -> dict:
    total = sum(e["weight"] for e in EVENT_TYPES)
    roll = rng.uniform(0, total)
    acc = 0
    for e in EVENT_TYPES:
        acc += e["weight"]
        if roll <= acc:
            return e
    return EVENT_TYPES[0]


def _pick_risk(rng: random.Random, candidates: list[str]) -> str:
    return rng.choice(candidates)


def _rand_time(rng: random.Random, start: datetime, end: datetime) -> datetime:
    span = (end - start).total_seconds()
    return start + timedelta(seconds=rng.uniform(0, max(span, 1)))


def _syslog_message(rng: random.Random, etype: dict, src_ip: str, asset_ip: str) -> str:
    """按事件类型生成日志消息"""
    t = etype["type"]
    if t == "brute_force":
        return (f"Failed password for root from {src_ip} port {rng.randint(10000, 65000)} ssh2 "
                f"(user=admin attempts={rng.randint(3, 40)})")
    if t == "web_attack":
        payload = rng.choice(["union select", "' or 1=1 --", "<script>alert(1)</script>", "../../../etc/passwd"])
        return f"WAF blocked SQLi/XSS attempt from {src_ip} to {asset_ip}: {payload}"
    if t == "malware":
        return f"Malware detected on {asset_ip} from {src_ip}: trojan.win32.{rng.choice(['emotet', 'qakbot', 'njrat'])}"
    if t == "dos":
        return f"Flood detected: {src_ip} -> {asset_ip} {rng.randint(5000, 80000)} pps SYN flood"
    if t == "phishing":
        return f"Phishing email blocked: from {src_ip} to user{rng.randint(1, 50)}@corp.local subject=invoice"
    if t == "lateral":
        return f"Lateral movement: {src_ip} -> {asset_ip} SMB {rng.randint(1, 20)} connections anomalous"
    return f"Policy violation: {asset_ip} accessed forbidden site from {src_ip}"


def generate_syslog_lines(count: int, window_start: str, window_end: str, seed: int = 42) -> list[str]:
    """生成 Syslog 行（RFC3164 简化：<PRI>Mmm dd hh:mm:ss host proc[pid]: msg）"""
    rng = random.Random(seed)
    start = datetime.strptime(window_start, "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(window_end, "%Y-%m-%d %H:%M:%S")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    lines = []
    for _ in range(count):
        etype = _pick_event_type(rng)
        src_ip = rng.choice(SRC_IPS)
        asset_ip = rng.choice(ASSET_IPS)
        device = rng.choice(DEVICES)
        ts = _rand_time(rng, start, end)
        pri = rng.choice([86, 134, 165, 190])  # auth/daemon 级别
        month = months[ts.month - 1]
        line = (f"<{pri}>{month} {ts.day:02d} {ts.strftime('%H:%M:%S')} {device} "
                f"{etype['type']}[{rng.randint(100, 9999)}]: {_syslog_message(rng, etype, src_ip, asset_ip)}")
        lines.append(line)
    return lines


def generate_api_alerts(count: int, window_start: str, window_end: str, seed: int = 7) -> list[dict]:
    """生成 API 告警（JSON 对象列表）"""
    rng = random.Random(seed)
    start = datetime.strptime(window_start, "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(window_end, "%Y-%m-%d %H:%M:%S")
    alerts = []
    for i in range(count):
        etype = _pick_event_type(rng)
        risk = _pick_risk(rng, etype["risk"])
        ts = _rand_time(rng, start, end)
        alerts.append({
            "id": f"AL-{ts.strftime('%Y%m%d')}-{i + 1:04d}",
            "time": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "alert_name": f"{etype['label']}告警",
            "event_type": etype["type"],
            "severity": risk,
            "src_ip": rng.choice(SRC_IPS),
            "dst_ip": rng.choice(ASSET_IPS),
            "device": rng.choice(DEVICES),
            "status": rng.choices(["open", "closed"], weights=[35, 65])[0],
            "rule_id": f"R-{rng.randint(100, 999)}",
        })
    return alerts


def generate_vulns(count: int, seed: int = 99) -> list[dict]:
    """生成漏洞台账（资产/漏洞维度）"""
    rng = random.Random(seed)
    vuln_names = [
        "Apache Log4j2 远程代码执行 (CVE-2021-44228)",
        "OpenSSH 弱口令爆破风险",
        "Nginx 目录遍历漏洞 (CVE-2022-41741)",
        "MySQL 未授权访问",
        "Redis 未授权访问",
        "Windows SMB 远程代码执行 (CVE-2020-0796)",
        "Tomcat 弱口令 + 后台部署",
        "Elasticsearch 未授权访问",
    ]
    items = []
    for _ in range(count):
        name = rng.choice(vuln_names)
        cvss = round(rng.uniform(3.0, 10.0), 1)
        risk = "HIGH" if cvss >= 7 else ("MEDIUM" if cvss >= 4 else "LOW")
        status = rng.choices(["unfixed", "fixed", "ignored"], weights=[60, 30, 10])[0]
        items.append({
            "asset_ip": rng.choice(ASSET_IPS),
            "asset_name": f"server-{rng.randint(1, 30)}",
            "vuln_name": name,
            "cvss": cvss,
            "risk_level": risk,
            "status": status,
            "discover_time": f"2026-0{rng.randint(1, 7)}-{rng.randint(1, 28):02d}",
            "source_name": "nessus-scan",
        })
    return items


def ensure_mock_files() -> dict:
    """生成并落盘 mock 数据文件（幂等），返回文件路径映射"""
    os.makedirs(MOCK_DIR, exist_ok=True)
    # 近 30 天窗口（联调默认）
    end = datetime.now()
    start = end - timedelta(days=30)
    ws = start.strftime("%Y-%m-%d %H:%M:%S")
    we = end.strftime("%Y-%m-%d %H:%M:%S")

    syslog_path = os.path.join(MOCK_DIR, "syslog.log")
    api_path = os.path.join(MOCK_DIR, "api_alerts.jsonl")
    vuln_path = os.path.join(MOCK_DIR, "vulns.csv")

    if not os.path.exists(syslog_path):
        lines = generate_syslog_lines(1200, ws, we)
        with open(syslog_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"[MOCK] syslog 已生成: {syslog_path} ({len(lines)} 行)")

    if not os.path.exists(api_path):
        alerts = generate_api_alerts(350, ws, we)
        with open(api_path, "w", encoding="utf-8") as f:
            for a in alerts:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
        logger.info(f"[MOCK] api 告警已生成: {api_path} ({len(alerts)} 条)")

    if not os.path.exists(vuln_path):
        vulns = generate_vulns(60)
        with open(vuln_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(vulns[0].keys()))
            writer.writeheader()
            writer.writerows(vulns)
        logger.info(f"[MOCK] 漏洞台账已生成: {vuln_path} ({len(vulns)} 条)")

    return {"syslog": syslog_path, "api": api_path, "vuln": vuln_path}
