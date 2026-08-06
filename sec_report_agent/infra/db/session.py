"""数据库会话 — MySQL8 默认 / SQLite 兜底（URL 切换即生效）"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config.settings import settings, _PROJECT_ROOT
from common.logger.logger import LogManager

logger = LogManager.get_logger()


def _normalize_url(url: str) -> str:
    """SQLite 相对路径转为基于项目根目录的绝对路径（避免 cwd 依赖）"""
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1)
        if not os.path.isabs(path):
            path = os.path.join(_PROJECT_ROOT, path)
        return f"sqlite:///{path}"
    return url


DATABASE_URL = _normalize_url(settings.database_url)

_engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs = {"connect_args": {"check_same_thread": False}}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：请求级会话"""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """启动时建表（幂等）"""
    from infra.db.base import Base
    from model.entity import entities  # noqa: F401  确保实体已注册
    Base.metadata.create_all(bind=engine)
    logger.info(f"[DB] 建表完成: {DATABASE_URL.split('://')[0]}")
