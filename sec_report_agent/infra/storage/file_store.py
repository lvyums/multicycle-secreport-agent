"""文件存储 — 报告文件规范命名与归档管理

目录规范：{REPORT_ROOT}/{cycle}/{YYYY}/{MM}/{cycle}_{YYYYMMDD_HHMMSS}_{version_no}.{ext}
"""

import os
from datetime import datetime
from typing import Optional

from config.settings import settings
from common.logger.logger import LogManager

logger = LogManager.get_logger()


def _safe_cycle(cycle: str) -> str:
    return cycle.lower() if cycle else "unknown"


def build_report_path(cycle: str, version_no: int = 1, ext: str = "md") -> str:
    """生成报告文件路径（自动建目录）"""
    now = datetime.now()
    cycle_dir = _safe_cycle(cycle)
    rel_dir = os.path.join(cycle_dir, str(now.year), f"{now.month:02d}")
    abs_dir = os.path.join(settings.report_root, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    filename = f"{cycle_dir}_{now.strftime('%Y%m%d_%H%M%S')}_v{version_no}.{ext}"
    return os.path.join(abs_dir, filename)


def save_file(content: str, file_path: str) -> str:
    """保存文本内容到文件（UTF-8），返回绝对路径"""
    abs_path = os.path.abspath(file_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"[STORAGE] 文件已保存: {abs_path} ({len(content)} 字符)")
    return abs_path


def read_file(file_path: str) -> str:
    """读取文本文件，不存在返回空串"""
    if not file_path or not os.path.exists(file_path):
        return ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"[STORAGE] 读取失败: {file_path}: {e}")
        return ""


def file_exists(file_path: str) -> bool:
    return bool(file_path) and os.path.exists(file_path)


def delete_file(file_path: str) -> bool:
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"[STORAGE] 文件已删除: {file_path}")
            return True
    except Exception as e:
        logger.error(f"[STORAGE] 删除失败: {file_path}: {e}")
    return False
