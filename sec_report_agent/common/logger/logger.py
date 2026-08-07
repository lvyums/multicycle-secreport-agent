"""统一日志管理器 — 单例模式，支持请求日志埋点

V2.4 深化：
  - 文件日志 JSON 结构化（Loki/ELK 零转换采集），控制台保持人类可读文本
  - 脱敏过滤器：敏感字段（settings.sensitive_fields 可配置，默认 password/secret/token/...）
    递归打码 ***，避免日志泄露凭据
  - 轮转：RotatingFileHandler 10MB × 5
"""

import json
import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

# 默认敏感字段（可用 settings.sensitive_fields 覆盖，逗号分隔）
DEFAULT_SENSITIVE_FIELDS = ["password", "secret", "token", "authorization",
                            "api_key", "apikey", "cookie", "x-api-key"]

_RESERVED = {"name", "msg", "args", "levelname", "levelno", "pathname", "filename",
             "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
             "created", "msecs", "relativeCreated", "thread", "threadName",
             "processName", "process", "taskName", "message", "asctime"}


def _sensitive_fields() -> list[str]:
    try:
        from config.settings import settings
        raw = getattr(settings, "sensitive_fields", "")
        if raw:
            return [f.strip().lower() for f in raw.split(",") if f.strip()]
    except Exception:
        pass
    return DEFAULT_SENSITIVE_FIELDS


def _is_sensitive(key, fields: list[str]) -> bool:
    kl = str(key).lower()
    return any(f in kl for f in fields)


def mask_value(value, fields: list[str]):
    """递归脱敏：dict 按 key 匹配敏感字段打码；list/tuple 递归"""
    if isinstance(value, dict):
        return {k: ("***" if _is_sensitive(k, fields) else mask_value(v, fields))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_value(v, fields) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    """JSON 结构化格式器（文件日志用）"""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": getattr(record, "trace_id", ""),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        # extra 字段（递归脱敏）
        extra = {}
        for k, v in record.__dict__.items():
            if k not in _RESERVED and not k.startswith("_"):
                extra[k] = v
        if extra:
            data["fields"] = mask_value(extra, _sensitive_fields())
        return json.dumps(data, ensure_ascii=False)


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

        text_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 控制台输出（文本，人类可读）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        try:
            import codecs
            if sys.platform == "win32":
                console_handler.stream = codecs.getwriter("utf-8")(sys.stdout.buffer, "replace")
        except (AttributeError, ImportError):
            pass
        console_handler.setFormatter(text_formatter)
        self._logger.addHandler(console_handler)

        # 文件日志 — JSON 结构化 + 自动分割（10MB × 5）
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
            file_handler.setFormatter(JsonFormatter())
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
