"""统一日志管理器 — 单例模式，支持请求日志埋点"""

import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


class LogManager:
    """全局日志管理器，单例模式，统一日志级别/格式/输出"""

    _instance: Optional["LogManager"] = None
    _initialized: bool = False

    def __new__(cls) -> "LogManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._logger = logging.getLogger("SecReportAgent")
        self._logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 控制台输出
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        try:
            import codecs
            if sys.platform == "win32":
                console_handler.stream = codecs.getwriter("utf-8")(sys.stdout.buffer, "replace")
        except (AttributeError, ImportError):
            pass
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        # 文件日志 — 自动分割
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(log_dir, exist_ok=True)
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, "app.log"),
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)
        except Exception:
            pass  # 文件日志非必需，失败不阻塞

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @classmethod
    def get_logger(cls) -> logging.Logger:
        return cls()._logger

    def set_level(self, level: int):
        self._logger.setLevel(level)

    @classmethod
    def log_request(cls, method: str, path: str, client_ip: str, duration_ms: int = 0):
        """记录接口请求日志"""
        cls.get_logger().info(f"[REQ] {method} {path} from {client_ip} [{duration_ms}ms]")

    @classmethod
    def log_ai_call(cls, provider: str, model: str, success: bool, duration_ms: int, error: str = ""):
        """记录 AI 调用日志"""
        status = "OK" if success else "FAIL"
        cls.get_logger().info(f"[AI] {provider}/{model} {status} {duration_ms}ms {error}")
