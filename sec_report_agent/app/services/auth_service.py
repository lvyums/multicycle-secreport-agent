"""认证服务（V2.0 RBAC）— pbkdf2 密码哈希 + hmac 自签 token，零新增依赖
V2.2：SECRET_KEY 收口到 settings（生产必须 env 注入强随机值）；登录失败锁定支持。
"""

import base64
import hashlib
import hmac
import json
import os
import time

from config.settings import settings

TOKEN_TTL = 12 * 3600  # 12 小时
_SECRET = settings.secret_key


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        dk = base64.b64decode(dk_b64)
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return hmac.compare_digest(calc, dk)
    except Exception:
        return False


def create_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "uid": user_id, "user": username, "role": role,
        "exp": int(time.time()) + TOKEN_TTL,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_token(token: str) -> dict | None:
    """解析并校验 token，返回 payload 或 None"""
    try:
        body, sig = token.split(".")
        expect = hmac.new(_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        pad = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None
