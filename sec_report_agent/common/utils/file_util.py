"""文件读写与上传处理工具"""

import os
from pathlib import Path
from typing import Optional


def read_file(file_path: str, encoding: str = "utf-8") -> Optional[str]:
    """读取文本文件内容，失败返回 None"""
    try:
        with open(file_path, "r", encoding=encoding) as f:
            return f.read()
    except (FileNotFoundError, UnicodeDecodeError, IOError) as e:
        from common.logger import LogManager
        LogManager.get_logger().error(f"读取文件失败 {file_path}: {e}")
        return None


def save_file(content: str, file_path: str, encoding: str = "utf-8") -> bool:
    """保存文本内容到文件"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except IOError as e:
        from common.logger import LogManager
        LogManager.get_logger().error(f"保存文件失败 {file_path}: {e}")
        return False


def parse_upload_file(file_path: str) -> list[str]:
    """解析上传的日志文件，按行分割，过滤空行"""
    content = read_file(file_path)
    if content is None:
        return []
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return lines


def get_file_extension(file_path: str) -> str:
    """获取文件扩展名（小写）"""
    return Path(file_path).suffix.lower()