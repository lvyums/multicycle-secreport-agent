"""缓存层 — Redis 默认 / 内存 TTL 兜底（CACHE_BACKEND 切换，业务无感）"""

import json
import threading
import time
from typing import Any, Optional

from config.settings import settings
from common.logger.logger import LogManager

logger = LogManager.get_logger()


class BaseCache:
    """缓存抽象接口"""

    def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl: int = 300):
        raise NotImplementedError

    def delete(self, key: str):
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError


class MemoryCache(BaseCache):
    """进程内 TTL 缓存（零依赖兜底实现）"""

    def __init__(self):
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expire_at, value = item
            if expire_at and time.time() > expire_at:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int = 300):
        expire_at = time.time() + ttl if ttl and ttl > 0 else 0
        with self._lock:
            self._data[key] = (expire_at, value)

    def delete(self, key: str):
        with self._lock:
            self._data.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None


class RedisCache(BaseCache):
    """Redis 实现（同步 redis-py，值统一 JSON 序列化）"""

    def __init__(self, url: str):
        import redis
        self._client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Optional[Any]:
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.warning(f"[CACHE] redis get 失败: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300):
        try:
            self._client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl if ttl > 0 else None)
        except Exception as e:
            logger.warning(f"[CACHE] redis set 失败: {e}")

    def delete(self, key: str):
        try:
            self._client.delete(key)
        except Exception as e:
            logger.warning(f"[CACHE] redis delete 失败: {e}")

    def exists(self, key: str) -> bool:
        try:
            return bool(self._client.exists(key))
        except Exception:
            return False


_cache_instance: Optional[BaseCache] = None


def get_cache() -> BaseCache:
    """缓存工厂（单例）：按 settings.cache_backend 返回实现"""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance
    if settings.cache_backend == "redis":
        try:
            _cache_instance = RedisCache(settings.redis_url)
            _cache_instance.set("__probe__", 1, ttl=5)
            logger.info("[CACHE] Redis 缓存就绪")
        except Exception as e:
            logger.warning(f"[CACHE] Redis 不可用，降级内存缓存: {e}")
            _cache_instance = MemoryCache()
    else:
        _cache_instance = MemoryCache()
        logger.info("[CACHE] 内存缓存就绪")
    return _cache_instance
