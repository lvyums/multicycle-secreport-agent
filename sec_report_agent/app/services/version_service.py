"""版本管理服务 — 初稿快照 / 列表 / 内容读取（备忘录模式：每次生成保存不可变快照）"""

from typing import Optional

from infra.db.session import SessionLocal
from infra.db.repositories import ReportVersionRepo, MetricSnapshotRepo, ReportTaskRepo
from infra.storage import file_store
from model.enum.enums import ReportStatus, VersionType
from common.exception.exception import NotFoundError
from common.logger.logger import LogManager

logger = LogManager.get_logger()


class VersionService:
    """报告版本服务"""

    # ── 快照创建 ──

    @staticmethod
    def create_draft(task_id: int, cycle: str, window_start: str, window_end: str,
                     title: str, content_md: str, file_path: str = "",
                     metric_snapshot_id: int = 0, operator: str = "system") -> dict:
        """创建 AI 初稿版本（版本号自动递增）"""
        db = SessionLocal()
        try:
            task = ReportTaskRepo.get(db, task_id)
            if not task:
                raise NotFoundError(f"任务不存在: {task_id}")
            version_no = ReportVersionRepo.next_version_no(db, task_id)
            ver = ReportVersionRepo.create(
                db, task_id=task_id, cycle=cycle,
                window_start=window_start, window_end=window_end,
                version_no=version_no, version_type=VersionType.AI_DRAFT.value,
                status=ReportStatus.DRAFT.value, title=title,
                content_md=content_md, file_path=file_path,
                metric_snapshot_id=metric_snapshot_id, operator=operator,
            )
            logger.info(f"[VERSION] 初稿已创建 #{ver.id} (task={task_id} v{version_no})")
            return VersionService._to_dict(ver)
        finally:
            db.close()

    # ── 查询 ──

    @staticmethod
    def get(version_id: int) -> dict:
        db = SessionLocal()
        try:
            ver = ReportVersionRepo.get(db, version_id)
            if not ver:
                raise NotFoundError(f"版本不存在: {version_id}")
            return VersionService._to_dict(ver)
        finally:
            db.close()

    @staticmethod
    def list_by_task(task_id: int) -> list[dict]:
        db = SessionLocal()
        try:
            versions = ReportVersionRepo.list_by_task(db, task_id)
            return [VersionService._to_dict(v) for v in versions]
        finally:
            db.close()

    @staticmethod
    def list_all(cycle: Optional[str] = None, page: int = 1, limit: int = 15,
                 keyword: Optional[str] = None) -> dict:
        db = SessionLocal()
        try:
            rows, total = ReportVersionRepo.list_all(
                db, cycle=cycle, offset=(page - 1) * limit, limit=limit, keyword=keyword,
            )
            return {
                "items": [VersionService._to_dict(v) for v in rows],
                "total": total,
                "page": page,
                "limit": limit,
            }
        finally:
            db.close()

    @staticmethod
    def get_content(version_id: int) -> dict:
        """返回版本内容（优先文件，其次 content_md）"""
        db = SessionLocal()
        try:
            ver = ReportVersionRepo.get(db, version_id)
            if not ver:
                raise NotFoundError(f"版本不存在: {version_id}")
            content = file_store.read_file(ver.file_path) if ver.file_path else ""
            if not content:
                content = ver.content_md or ""
            return {"version_id": version_id, "title": ver.title, "content": content}
        finally:
            db.close()

    @staticmethod
    def get_download(version_id: int) -> dict:
        """下载信息（返回文件路径，不存在时用 md 实时落盘）"""
        db = SessionLocal()
        try:
            ver = ReportVersionRepo.get(db, version_id)
            if not ver:
                raise NotFoundError(f"版本不存在: {version_id}")
            if ver.file_path and file_store.file_exists(ver.file_path):
                return {"version_id": version_id, "path": ver.file_path, "exists": True}
            # 无文件 → 落盘 md
            path = file_store.build_report_path(ver.cycle, ver.version_no, "md")
            file_store.save_file(ver.content_md or "", path)
            return {"version_id": version_id, "path": path, "exists": False}
        finally:
            db.close()

    # ── 工具 ──

    @staticmethod
    def _to_dict(ver) -> dict:
        return {
            "id": ver.id,
            "taskId": ver.task_id,
            "cycle": ver.cycle,
            "windowStart": ver.window_start,
            "windowEnd": ver.window_end,
            "versionNo": ver.version_no,
            "versionType": ver.version_type,
            "status": ver.status,
            "title": ver.title,
            "filePath": ver.file_path,
            "metricSnapshotId": ver.metric_snapshot_id,
            "operator": ver.operator,
            "remark": ver.remark,
            "createdAt": ver.created_at,
        }
