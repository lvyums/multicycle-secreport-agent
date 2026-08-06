"""Mock 数据生成器 — 确定性生成五类数据源原始数据（seed 固定，结果可复现）

覆盖窗口：2025-01-01 ～ 当前（全周期可验证：日报取昨天、年报取 2025 全年均有数据）

输出：
- Syslog 日志行（RFC3164 简化格式）→ data/mock/syslog.log
- API 告警 JSON 行 → data/mock/api_alerts.jsonl
- DB 漏洞台账 CSV → data/mock/vulns.csv
- Excel 威胁情报台账 → data/mock/threat_intel.xlsx
- 情报 IOC JSONL → data/mock/intel_iocs.jsonl
"""

import csv
import json
import os
import random
from datetime import datetime, timedelta

from common.logger.logger import LogManager

logger = LogManager.get_logger()

MOCK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "mock")

# 全年覆盖窗口（V1.2 全周期：日报/周报/月报/季报/年报均有数据）
FULL_START = "2025-01-01 00:00:00"
# 每日目标密度（约 40 条/天 syslog，20 条/天 api）
SYSLOG_PER_DAY = 40
API_PER_DAY = 20

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

INTEL_TYPES = ["勒索软件", "APT组织", "挖矿木马", "供应链攻击", "数据泄露", "0day漏洞"]
IOC_SOURCES = ["微步在线", "奇安信威胁情报", "AlienVault OTX", "自家蜜罐", "沙箱分析"]


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


def _full_window() -> tuple[str, str]:
    """全年覆盖窗口：2025-01-01 ～ now"""
    end = datetime.now()
    return FULL_START, end.strftime("%Y-%m-%d %H:%M:%S")


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
    """生成漏洞台账（资产/漏洞维度，发现时间覆盖 2025~2026 全年）"""
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
        year = rng.choice([2025, 2026])
        items.append({
            "asset_ip": rng.choice(ASSET_IPS),
            "asset_name": f"server-{rng.randint(1, 30)}",
            "vuln_name": name,
            "cvss": cvss,
            "risk_level": risk,
            "status": status,
            "discover_time": f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "source_name": "nessus-scan",
        })
    return items


def generate_threat_intel(count: int, seed: int = 2025) -> list[dict]:
    """生成威胁情报台账（Excel 数据源用）"""
    rng = random.Random(seed)
    items = []
    for i in range(count):
        year = rng.choice([2025, 2026])
        items.append({
            "情报名称": f"{rng.choice(INTEL_TYPES)}活动通报-{rng.randint(100, 999)}",
            "情报类型": rng.choice(INTEL_TYPES),
            "影响资产": rng.choice(ASSET_IPS),
            "置信度": rng.choice(["高", "中", "低"]),
            "发布时间": f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
            "来源": rng.choice(IOC_SOURCES),
            "处置建议": rng.choice(["封禁IOC", "升级补丁", "隔离主机", "加强监测"]),
        })
    return items


def generate_intel_iocs(count: int, seed: int = 88) -> list[dict]:
    """生成情报 IOC 列表（情报源适配器用）"""
    rng = random.Random(seed)
    iocs = []
    for i in range(count):
        itype = rng.choice(["ip", "domain", "hash"])
        if itype == "ip":
            value = f"203.0.113.{rng.randint(1, 254)}"
        elif itype == "domain":
            value = f"evil{rng.randint(1, 999)}.example.org"
        else:
            value = rng.choice(["a1b2c3d4e5f60718293a4b5c6d7e8f90",
                                "deadbeef00112233445566778899aabb",
                                "0123456789abcdef0123456789abcdef"])
        year = rng.choice([2025, 2026])
        iocs.append({
            "ioc_type": itype,
            "ioc_value": value,
            "confidence": rng.choice(["high", "medium", "low"]),
            "source": rng.choice(IOC_SOURCES),
            "first_seen": f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
            "tags": rng.sample(["apt", "malware", "botnet", "phishing", "scanner"], k=2),
        })
    return iocs


def _write_csv(path: str, items: list[dict]):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(items[0].keys()))
        writer.writeheader()
        writer.writerows(items)


def ensure_mock_files(force: bool = False) -> dict:
    """生成并落盘 mock 数据文件（覆盖全年窗口），返回文件路径映射

    force=True 时无论文件是否存在都重新生成（保证窗口覆盖最新日期）
    """
    os.makedirs(MOCK_DIR, exist_ok=True)
    ws, we = _full_window()
    days = (datetime.strptime(we, "%Y-%m-%d %H:%M:%S") - datetime.strptime(ws, "%Y-%m-%d %H:%M:%S")).days
    syslog_count = max(days * SYSLOG_PER_DAY, 500)
    api_count = max(days * API_PER_DAY, 200)

    paths = {
        "syslog": os.path.join(MOCK_DIR, "syslog.log"),
        "api": os.path.join(MOCK_DIR, "api_alerts.jsonl"),
        "vuln": os.path.join(MOCK_DIR, "vulns.csv"),
        "intel": os.path.join(MOCK_DIR, "threat_intel.xlsx"),
        "ioc": os.path.join(MOCK_DIR, "intel_iocs.jsonl"),
    }

    if force or not os.path.exists(paths["syslog"]):
        lines = generate_syslog_lines(syslog_count, ws, we)
        with open(paths["syslog"], "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"[MOCK] syslog 已生成: {paths['syslog']} ({len(lines)} 行)")

    if force or not os.path.exists(paths["api"]):
        alerts = generate_api_alerts(api_count, ws, we)
        with open(paths["api"], "w", encoding="utf-8") as f:
            for a in alerts:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
        logger.info(f"[MOCK] api 告警已生成: {paths['api']} ({len(alerts)} 条)")

    if force or not os.path.exists(paths["vuln"]):
        _write_csv(paths["vuln"], generate_vulns(120))
        logger.info(f"[MOCK] 漏洞台账已生成: {paths['vuln']}")

    if force or not os.path.exists(paths["intel"]):
        from openpyxl import Workbook
        items = generate_threat_intel(80)
        wb = Workbook()
        ws_obj = wb.active
        ws_obj.title = "威胁情报"
        ws_obj.append(list(items[0].keys()))
        for row in items:
            ws_obj.append(list(row.values()))
        wb.save(paths["intel"])
        logger.info(f"[MOCK] 威胁情报 xlsx 已生成: {paths['intel']} ({len(items)} 条)")

    if force or not os.path.exists(paths["ioc"]):
        iocs = generate_intel_iocs(150)
        with open(paths["ioc"], "w", encoding="utf-8") as f:
            for ioc in iocs:
                f.write(json.dumps(ioc, ensure_ascii=False) + "\n")
        logger.info(f"[MOCK] 情报 IOC 已生成: {paths['ioc']} ({len(iocs)} 条)")

    return paths


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    paths = ensure_mock_files(force=force)
    print("mock 文件就绪:")
    for k, v in paths.items():
        print(f"  {k}: {v} ({os.path.getsize(v)} bytes)")
