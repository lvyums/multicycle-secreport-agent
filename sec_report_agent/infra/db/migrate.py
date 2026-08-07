"""轻量列迁移（V2.2）— 为已存在的表补充新列，兼容 SQLite / MySQL

背景：项目无 Alembic，Base.metadata.create_all 不会为已存在表加列。
V2.2 给 sys_user 新增 must_change_pwd / login_fail_count / locked_until，
老库（MySQL 开发库 / SQLite）需 ALTER TABLE 补齐。
"""

from sqlalchemy import text

from common.logger.logger import LogManager

logger = LogManager.get_logger()

# 迁移清单：表名 -> {列名: DDL 片段}
MIGRATIONS: dict[str, dict[str, str]] = {
    "sys_user": {
        "must_change_pwd": "VARCHAR(8) DEFAULT 'no'",
        "login_fail_count": "INTEGER DEFAULT 0",
        "locked_until": "VARCHAR(32) DEFAULT ''",
    },
}


def _existing_columns(db, table: str) -> set[str]:
    """获取表已有列名（SQLite 用 PRAGMA，MySQL 用 information_schema）"""
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    if dialect == "sqlite":
        rows = db.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}
    rows = db.execute(
        text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}'"
        )
    ).fetchall()
    return {r[0] for r in rows}


def run_migrations(db) -> list[str]:
    """执行所有缺失列迁移，返回已执行的列名列表（幂等）"""
    applied: list[str] = []
    for table, columns in MIGRATIONS.items():
        existing = _existing_columns(db, table)
        for col, ddl in columns.items():
            if col in existing:
                continue
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
            applied.append(f"{table}.{col}")
            logger.info(f"[MIGRATE] {table} 增加列 {col} ({ddl})")
    if applied:
        db.commit()
    return applied
