"""V1.3 后端测试 — 数据源 CRUD / 知识库 / 报告选配 / 章节裁剪 / 自动推送"""
import sys
sys.path.insert(0, ".")

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ── 数据源零代码 CRUD ──

def test_datasource_meta():
    r = client.get("/api/datasource/meta")
    assert r.status_code == 200
    types = r.json()["data"]["types"]
    assert len(types) >= 6
    # 每种类型都有表单字段定义（零代码驱动）
    for meta in types.values():
        assert "label" in meta
        assert isinstance(meta.get("fields"), list)


def test_datasource_crud_flow():
    # 创建
    r = client.post("/api/datasource/create", json={
        "name": "ut-test-src", "type": "SYSLOG",
        "config": {"file_path": "/tmp/ut.log"},
        "syncStrategy": "window", "description": "UT",
    })
    assert r.status_code == 200
    sid = r.json()["data"]["id"]
    # 列表包含
    rows = client.get("/api/datasource/list").json()["data"]["items"]
    assert any(x["id"] == sid for x in rows)
    # 停用
    r = client.post("/api/datasource/toggle", json={"id": sid})
    assert r.json()["data"]["status"] == "disabled"
    # 更新
    r = client.post("/api/datasource/update", json={"id": sid, "description": "UT-改"})
    assert r.status_code == 200
    # 删除
    r = client.post("/api/datasource/delete", json={"id": sid})
    assert r.json()["data"]["id"] == sid


# ── 知识库 ──

def test_kb_crud_and_categories():
    cats = client.get("/api/kb/categories").json()["data"]["categories"]
    assert len(cats) >= 1
    # 创建
    r = client.post("/api/kb/create", json={
        "title": "UT文档", "category": "attack", "content": "SSH 爆破特征：连续失败登录",
    })
    assert r.status_code == 200
    kid = r.json()["data"]["id"]
    # 列表
    rows = client.get("/api/kb/list").json()["data"]["items"]
    assert any(x["id"] == kid for x in rows)
    # 启停（toggle 应翻转状态）
    r = client.post("/api/kb/toggle", json={"id": kid})
    st1 = r.json()["data"]["enabled"]
    r2 = client.post("/api/kb/toggle", json={"id": kid})
    st2 = r2.json()["data"]["enabled"]
    assert st1 != st2
    # 删除
    client.post("/api/kb/delete", json={"id": kid})


# ── 报告选配 ──

def test_report_config_get_save():
    r = client.get("/api/config/report/get")
    assert r.status_code == 200
    d = r.json()["data"]
    assert "sections" in d and "pushChannels" in d and "autoGenerate" in d
    # 保存
    r = client.post("/api/config/report/save", json={
        "sections": {"overview": True, "alert": True, "vuln": False,
                     "attack": True, "trend": True, "suggestion": True},
        "pushChannels": ["local"], "autoGenerate": "disabled",
    })
    assert r.status_code == 200
    d2 = client.get("/api/config/report/get").json()["data"]
    assert d2["sections"]["vuln"] is False


# ── 章节裁剪（单元） ──

def test_filter_sections():
    from app.services.report_service import ReportService
    md = (
        "# 标题\n\n"
        "## 一、总体态势\n正文A\n"
        "## 二、告警分析\n正文B\n"
        "## 三、漏洞情况\n正文C\n"
        "## 四、攻击行为研判\n正文D\n"
    )
    out = ReportService._filter_sections(md, {
        "overview": True, "alert": True, "vuln": False,
        "attack": True, "trend": True, "suggestion": True,
    })
    assert "漏洞情况" not in out
    assert "总体态势" in out and "攻击行为" in out
    # 未配置 → 不裁剪
    assert ReportService._filter_sections(md, None) == md
