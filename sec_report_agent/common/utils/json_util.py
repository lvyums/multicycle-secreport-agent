"""JSON 配置文件加载与缓存工具"""

import json
import os
from typing import Optional, Any, Union
from threading import Lock

from common.logger import LogManager
from common.file_util import read_file

logger = LogManager.get_logger()


class JsonConfigLoader:
    """JSON 配置文件加载器 — 支持缓存和热加载"""

    _cache: dict[str, dict] = {}
    _lock = Lock()

    @classmethod
    def load(cls, file_path: str, use_cache: bool = True) -> Optional[Union[dict, list]]:
        """加载 JSON 配置文件，支持缓存"""
        abs_path = os.path.abspath(file_path)

        if use_cache and abs_path in cls._cache:
            return cls._cache[abs_path]

        content = read_file(abs_path)
        if content is None:
            logger.warning(f"配置文件读取失败: {abs_path}")
            return None

        try:
            data = json.loads(content)
            with cls._lock:
                cls._cache[abs_path] = data
            logger.debug(f"加载配置文件: {abs_path}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败 {abs_path}: {e}")
            return None

    @classmethod
    def reload(cls, file_path: str) -> Optional[dict]:
        """强制重新加载配置文件（忽略缓存）"""
        abs_path = os.path.abspath(file_path)
        with cls._lock:
            cls._cache.pop(abs_path, None)
        return cls.load(abs_path, use_cache=False)

    @classmethod
    def get(cls, file_path: str, key: str = "", default: Any = None) -> Any:
        """获取配置值，支持嵌套 key（用点分隔）"""
        data = cls.load(file_path)
        if data is None:
            return default

        if not key:
            return data

        keys = key.split(".")
        current = data
        for k in keys:
            if isinstance(current, dict):
                current = current.get(k)
            else:
                return default
            if current is None:
                return default
        return current

    @classmethod
    def clear_cache(cls, file_path: Optional[str] = None):
        """清除缓存"""
        with cls._lock:
            if file_path:
                cls._cache.pop(os.path.abspath(file_path), None)
            else:
                cls._cache.clear()
