"""pytest 全局配置 — RBAC 依赖覆盖（V2.0）：
测试默认以 admin 身份运行，现有无 token 用例不受影响；
RBAC 专项测试用 override 切换角色验证 401/403。

⚠️ 测试隔离（V2.0 修复）：在 import 业务代码之前把 DATABASE_URL 切到独立
SQLite 测试库，防止测试数据污染开发 MySQL（曾导致历史报告列表出现
"UT版本/基线/目标" 等 stub 版本、预览无内容）。
"""
import os
os.environ["DATABASE_URL"] = os.environ.get("SEC_REPORT_TEST_DB", "sqlite:///./test_sec_report.db")

import sys
sys.path.insert(0, ".")

import pytest
from fastapi.testclient import TestClient

from main import app
from api.auth_deps import get_current_user
from model.entity.entities import User


@pytest.fixture(scope="session", autouse=True)
def _rbac_admin_override():
    """会话级：默认注入 admin 用户（依赖覆盖，绕过 token 校验）"""
    admin = User(id=999, username="ut-admin", role="admin", enabled="enabled")
    app.dependency_overrides[get_current_user] = lambda: admin
    yield
    app.dependency_overrides.clear()


@pytest.fixture(scope="session", autouse=True)
def _test_datasources():
    """会话级：测试库建 mock 数据源配置（幂等）— 否则独立 SQLite 无数据源 → 0 事件 → EMPTY"""
    from capability.adapter.mock_data_gen import ensure_mock_files
    from infra.db.session import SessionLocal, init_db
    from infra.db.repositories import DataSourceConfigRepo
    init_db()
    paths = ensure_mock_files()
    db = SessionLocal()
    try:
        existing = {c.name for c in DataSourceConfigRepo.list_all(db)}
        specs = [
            ("mock-syslog", "SYSLOG", {"file_path": paths["syslog"]}, "Syslog 模拟日志源"),
            ("mock-api", "API", {"file_path": paths["api"]}, "告警平台模拟 API"),
            ("mock-db", "DB", {"file_path": paths["vuln"]}, "资产漏洞台账模拟"),
            ("mock-intel-xlsx", "EXCEL", {"file_path": paths["intel"]}, "威胁情报台账模拟"),
            ("mock-intel-ioc", "INTEL", {"file_path": paths["ioc"]}, "威胁情报 IOC 模拟"),
            ("mock-history", "HISTORY", {"cycle": "MONTHLY"}, "历史报告环比源"),
        ]
        for name, stype, cfg, desc in specs:
            if name not in existing:
                DataSourceConfigRepo.create(db, name=name, type=stype, status="enabled",
                                            config_json=cfg, description=desc)
    finally:
        db.close()
    yield


@pytest.fixture()
def rbac_override():
    """按角色注入当前用户：rbac_override("viewer") / ("analyst") / ("admin")"""
    def _apply(role: str):
        user = User(id=1, username=f"ut-{role}", role=role, enabled="enabled")
        app.dependency_overrides[get_current_user] = lambda: user
        return user
    yield _apply
    admin = User(id=999, username="ut-admin", role="admin", enabled="enabled")
    app.dependency_overrides[get_current_user] = lambda: admin


@pytest.fixture(scope="session")
def client() -> TestClient:
    """共享 TestClient（lifespan 不触发，建表由用例内 init_db 完成）"""
    return TestClient(app)
