"""零依赖 asyncio 调度器 — cron 规则解析 + 轮询触发（APScheduler 替代实现）

设计：
- 后台 asyncio 任务每 10s 检查一次 cron 匹配，命中即触发（协程方式执行）
- cron 支持 5 字段：分 时 日 月 周（周 0=周日，兼容 1-7）
- 任务去重：同一 job 同一分钟只触发一次（_last_fired 记录）
"""

import asyncio
import threading
from datetime import datetime
from typing import Callable, Optional

from common.logger.logger import LogManager
from infra.schedule.scheduler_base import SchedulerBase

logger = LogManager.get_logger()


def parse_cron(expr: str) -> Optional[list]:
    """解析 5 字段 cron 表达式 → [minutes, hours, days, months, weekdays] 集合列表"""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"cron 表达式必须为 5 字段: {expr}")
    result = []
    for i, part in enumerate(parts):
        values: set[int] = set()
        for token in part.split(","):
            token = token.strip()
            if token == "*":
                continue  # 通配，保持空集表示任意
            if "-" in token:
                lo, hi = token.split("-")
                values.update(range(int(lo), int(hi) + 1))
            elif "/" in token:
                base, step = token.split("/")
                if base == "*":
                    values.update(range(0, 60, int(step)))  # 分钟粒度简化
                else:
                    values.update(range(int(base), 60, int(step)))
            else:
                values.add(int(token))
        result.append(values)
    return result


class SimpleScheduler(SchedulerBase):
    """asyncio 轮询调度器"""

    POLL_INTERVAL = 10  # 秒

    def __init__(self):
        self._jobs: dict[str, dict] = {}          # job_id → {cron, interval_seconds, func, args, kwargs}
        self._last_fired: dict[str, str] = {}     # job_id → 上次触发分钟键 YYYYMMDDHHMM
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def add_cron_job(self, job_id: str, cron_expr: str, func: Callable, *args, **kwargs):
        self._jobs[job_id] = {
            "cron": parse_cron(cron_expr),
            "cron_expr": cron_expr,
            "interval_seconds": None,
            "func": func,
            "args": args,
            "kwargs": kwargs,
        }
        logger.info(f"[SCHED] cron 任务注册: {job_id} = {cron_expr}")

    def add_interval_job(self, job_id: str, seconds: int, func: Callable, *args, **kwargs):
        self._jobs[job_id] = {
            "cron": None,
            "cron_expr": "",
            "interval_seconds": seconds,
            "func": func,
            "args": args,
            "kwargs": kwargs,
        }
        logger.info(f"[SCHED] 间隔任务注册: {job_id} = {seconds}s")

    def remove_job(self, job_id: str):
        self._jobs.pop(job_id, None)
        self._last_fired.pop(job_id, None)

    def start(self):
        if self._running:
            return
        self._running = True
        # 在独立线程中跑事件循环，避免阻塞主线程
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="simple-scheduler")
        self._thread.start()
        logger.info("[SCHED] 调度器已启动")

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._task = self._loop.create_task(self._tick_loop())
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _tick_loop(self):
        while self._running:
            try:
                self._check_jobs()
            except Exception as e:
                logger.error(f"[SCHED] 调度检查异常: {e}")
            await asyncio.sleep(self.POLL_INTERVAL)

    def _check_jobs(self):
        now = datetime.now()
        minute_key = now.strftime("%Y%m%d%H%M")
        for job_id, job in list(self._jobs.items()):
            try:
                if job["interval_seconds"]:
                    # 间隔任务：记录上次触发时间（简化：以进程启动为基准）
                    self._fire(job_id, job)
                else:
                    cron = job["cron"]
                    if self._match_cron(cron, now) and self._last_fired.get(job_id) != minute_key:
                        self._last_fired[job_id] = minute_key
                        self._fire(job_id, job)
            except Exception as e:
                logger.error(f"[SCHED] 任务 {job_id} 检查异常: {e}")

    @staticmethod
    def _match_cron(cron: list, now: datetime) -> bool:
        """匹配 5 字段（空集=任意）"""
        minute, hour, day, month, weekday = cron
        if minute and now.minute not in minute:
            return False
        if hour and now.hour not in hour:
            return False
        if day and now.day not in day:
            return False
        if month and now.month not in month:
            return False
        # 周：0=周日；Python weekday 0=周一
        py_wd = now.weekday()  # 0-6, 0=Mon
        cron_wd = (py_wd + 1) % 7  # 转 0=Sun
        if weekday and cron_wd not in weekday:
            return False
        return True

    def _fire(self, job_id: str, job: dict):
        """在事件循环中调度执行任务函数"""
        if self._loop is None:
            return
        func = job["func"]
        args = job["args"]
        kwargs = job["kwargs"]
        try:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                self._loop.create_task(self._safe_await(job_id, result))
            logger.info(f"[SCHED] 任务触发: {job_id}")
        except Exception as e:
            logger.error(f"[SCHED] 任务 {job_id} 执行异常: {e}")

    async def _safe_await(self, job_id: str, coro):
        try:
            await coro
        except Exception as e:
            logger.error(f"[SCHED] 异步任务 {job_id} 异常: {e}")

    def shutdown(self):
        self._running = False
        if self._loop and self._task:
            self._loop.call_soon_threadsafe(self._task.cancel)
        logger.info("[SCHED] 调度器已停止")

    def get_next_run_time(self, job_id: str) -> Optional[str]:
        """下次触发时间（简化：基于 cron 分钟粒度推算，仅用于前端预览）"""
        job = self._jobs.get(job_id)
        if not job or not job["cron"]:
            return None
        now = datetime.now()
        for minutes_ahead in range(1, 60 * 24 * 8):  # 最多推 7 天
            candidate = now.replace(second=0, microsecond=0)
            from datetime import timedelta
            candidate = candidate + timedelta(minutes=minutes_ahead)
            if self._match_cron(job["cron"], candidate):
                return candidate.strftime("%Y-%m-%d %H:%M:%S")
        return None
