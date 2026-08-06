"""调度抽象 — add_job(cron/interval, func) 统一接口，可替换实现"""

from abc import ABC, abstractmethod
from typing import Callable, Optional


class SchedulerBase(ABC):
    """调度器抽象接口"""

    @abstractmethod
    def add_cron_job(self, job_id: str, cron_expr: str, func: Callable, *args, **kwargs):
        """按 cron 表达式注册任务（5 字段：分 时 日 月 周）"""
        ...

    @abstractmethod
    def add_interval_job(self, job_id: str, seconds: int, func: Callable, *args, **kwargs):
        """按固定间隔注册任务（测试/演示用）"""
        ...

    @abstractmethod
    def remove_job(self, job_id: str):
        ...

    @abstractmethod
    def start(self):
        """启动调度循环（非阻塞或后台线程）"""
        ...

    @abstractmethod
    def shutdown(self):
        ...

    @abstractmethod
    def get_next_run_time(self, job_id: str) -> Optional[str]:
        """下次触发时间（ISO 字符串，用于前端预览）"""
        ...
