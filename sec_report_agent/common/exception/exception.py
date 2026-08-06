"""自定义异常体系 — 全局业务异常统一收口

异常层级：
    SecReportError（基类）
    ├── BusinessError      业务规则违反（参数/状态机非法跳转等）
    ├── NotFoundError      资源不存在
    ├── DataSourceError    数据源接入/解析失败
    ├── ScheduleError      调度/任务执行异常
    ├── LLMError           LLM 调用异常（调用方应自行降级，此处为兜底）
    ├── TemplateError      模板渲染/加载失败
    ├── StorageError       文件存储/读取失败
    └── AuthError          认证/权限不足
"""

from typing import Optional


class SecReportError(Exception):
    """业务异常基类"""

    def __init__(self, message: str, code: int = 500, data: Optional[dict] = None):
        self.message = message
        self.code = code
        self.data = data or {}
        super().__init__(message)


class BusinessError(SecReportError):
    def __init__(self, message: str, code: int = 1001, data: Optional[dict] = None):
        super().__init__(message, code=code, data=data)


class NotFoundError(SecReportError):
    def __init__(self, message: str = "资源不存在", code: int = 404, data: Optional[dict] = None):
        super().__init__(message, code=code, data=data)


class DataSourceError(SecReportError):
    def __init__(self, message: str = "数据源接入失败", code: int = 2001, data: Optional[dict] = None):
        super().__init__(message, code=code, data=data)


class ScheduleError(SecReportError):
    def __init__(self, message: str = "调度执行异常", code: int = 3001, data: Optional[dict] = None):
        super().__init__(message, code=code, data=data)


class LLMError(SecReportError):
    def __init__(self, message: str = "LLM 调用失败", code: int = 4001, data: Optional[dict] = None):
        super().__init__(message, code=code, data=data)


class TemplateError(SecReportError):
    def __init__(self, message: str = "模板渲染失败", code: int = 5001, data: Optional[dict] = None):
        super().__init__(message, code=code, data=data)


class StorageError(SecReportError):
    def __init__(self, message: str = "文件存储失败", code: int = 6001, data: Optional[dict] = None):
        super().__init__(message, code=code, data=data)


class AuthError(SecReportError):
    def __init__(self, message: str = "认证失败", code: int = 401, data: Optional[dict] = None):
        super().__init__(message, code=code, data=data)
