"""pytest 全局配置 — RBAC 依赖覆盖（V2.0）：
测试默认以 admin 身份运行，现有无 token 用例不受影响；
RBAC 专项测试用 override 切换角色验证 401/403。
"""
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
