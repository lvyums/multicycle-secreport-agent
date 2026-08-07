"""V2.4.1 知识库示例文档补种 — 通过 /api/kb/create 创建(自动同步向量库)"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE = "http://127.0.0.1:8001"

DOCS = [
    {
        "title": "暴力破解攻击特征与处置建议",
        "category": "attack",
        "content": (
            "暴力破解(Brute Force)攻击特征：短时间内产生大量登录失败记录、单一源IP或多个源IP集中尝试、"
            "针对同一账号批量尝试弱口令、用户名枚举探测、登录时间分布异常。研判要点：失败次数超过阈值"
            "（如5分钟内同一IP失败超过20次）即可判定为暴力破解；结合目标端口(22/3389/3306)判断爆破面。"
            "处置建议：封禁攻击源IP并联动威胁情报、启用多因素认证、整改弱口令与默认口令、登录接口限流"
            "与验证码、将失败日志接入SIEM持续监控。统计口径：暴力破解通常占全网攻击事件首位，需按源IP"
            "聚合去重统计攻击源数量。"
        ),
    },
    {
        "title": "Web攻击主要类型与研判要点",
        "category": "attack",
        "content": (
            "Web攻击常见类型：SQL注入(特征：请求参数含select/union/单引号闭合)、跨站脚本XSS(特征："
            "脚本标签、事件属性注入)、路径遍历(特征：../目录穿越)、命令注入、扫描探测(特征：大量404/"
            "异常User-Agent)。研判要点：按请求特征与返回码聚类，区分真实利用与扫描探测；SQL注入按"
            "数据库报错特征确认是否成功利用；XSS按浏览器执行上下文判定危害。处置建议：Web应用防火墙"
            "规则拦截、输入输出校验、参数化查询、及时修补框架漏洞、敏感接口限流。"
        ),
    },
    {
        "title": "安全事件闭环处置流程与优先级",
        "category": "defense",
        "content": (
            "事件闭环处置流程：发现→研判→处置→验证→复盘五步。优先级判定：高危事件(核心资产沦陷、"
            "数据泄露、横向移动迹象)需30分钟内响应、2小时内处置；中危事件(扫描探测、弱口令尝试)需"
            "2小时内响应、24小时内闭环；低危事件按常规流程闭环。闭环率指标：已闭环事件数/总事件数，"
            "行业建议基线不低于80%；闭环率低于阈值说明处置流程存在瓶颈，需优化自动化响应与工单流转。"
            "复盘输出：事件原因、根因分析、改进措施，沉淀为处置知识库。"
        ),
    },
    {
        "title": "网安态势报告指标口径说明",
        "category": "regulation",
        "content": (
            "报告指标口径：综合风险等级按告警总量、高危占比、闭环率、漏洞存量综合判定(高/中/低)。"
            "高危判定：告警总量超过阈值或高危事件占比过高；闭环率低于80%触发风险标记。事件类型分类："
            "暴力破解brute_force、Web攻击web_attack、恶意软件malware、拒绝服务dos、钓鱼phishing、"
            "横向移动lateral、策略违规policy、威胁情报threat_intel。环比/同比口径：本期窗口对比上一"
            "同周期窗口，需先有历史快照；日均事件数=窗口事件总量/窗口天数。趋势分析建议：按天分布"
            "观察周期性波动，结合历史报告对比识别上升/下降趋势。"
        ),
    },
]

def call(path, data=None, method="POST"):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

token = call("/api/auth/login", {"username": "admin", "password": "admin123"}, "POST")["data"]["token"]


def api(path, data=None, method="POST"):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + token})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


for d in DOCS:
    # 幂等：标题已存在则跳过
    existing = api("/api/kb/list", None, "GET")["data"]["items"]
    if any(i["title"] == d["title"] for i in existing):
        print("skip(已存在):", d["title"])
        continue
    r = api("/api/kb/create", d)
    print("created:", r["data"]["id"], d["title"])

# 验证向量库
from capability.rag.rag_factory import RAGFactory
for kb in ("threat_intel", "report_guideline"):
    print(kb, "count:", RAGFactory.get_kb(kb).store.count())

# 验证召回
from capability.rag.rag_facade import RAGFacade
refs = RAGFacade().recall("暴力破解攻击怎么处置？", top_k=3)
print("recall refs:", len(refs))
for r in refs:
    print(" -", r["kb_label"], "|", r["title"], "| score:", r["score"])
