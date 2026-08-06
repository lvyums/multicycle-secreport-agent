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


class VersionCompareService:
    """版本对比服务（V1.2）：指标 diff + 章节文本 diff"""

    # 参与对比的数值指标（白名单，避免 by_day/by_type 数组噪音）
    METRIC_FIELDS = [
        ("alert", "total", "告警总量"),
        ("alert", "high", "高危告警"),
        ("alert", "medium", "中危告警"),
        ("alert", "low", "低危告警"),
        ("alert", "info", "提示告警"),
        ("alert", "close_rate", "事件闭环率"),
        ("vuln", "total", "漏洞总量"),
        ("vuln", "unfixed", "未修复漏洞"),
        ("vuln", "unfixed_high", "未修复高危漏洞"),
        ("vuln", "close_rate", "漏洞修复率"),
    ]

    @staticmethod
    def compare(db, base_id: int, target_id: int) -> dict:
        from infra.db.repositories import ReportVersionRepo, MetricSnapshotRepo

        base = ReportVersionRepo.get(db, base_id)
        target = ReportVersionRepo.get(db, target_id)
        if not base or not target:
            from common.exception.exception import NotFoundError
            raise NotFoundError(f"版本不存在: {base_id if not base else target_id}")

        base_metrics = VersionCompareService._load_metrics(db, base)
        target_metrics = VersionCompareService._load_metrics(db, target)

        return {
            "base": {"id": base.id, "title": base.title, "cycle": base.cycle,
                     "windowStart": base.window_start, "windowEnd": base.window_end,
                     "createdAt": base.created_at},
            "target": {"id": target.id, "title": target.title, "cycle": target.cycle,
                       "windowStart": target.window_start, "windowEnd": target.window_end,
                       "createdAt": target.created_at},
            "metricDiff": VersionCompareService._metric_diff(base_metrics, target_metrics),
            "textDiff": VersionCompareService._text_diff(base.content_md, target.content_md),
        }

    @staticmethod
    def _load_metrics(db, ver) -> dict:
        from infra.db.repositories import MetricSnapshotRepo
        snap = MetricSnapshotRepo.get(db, ver.metric_snapshot_id) if ver.metric_snapshot_id else None
        return (snap.metrics_json or {}) if snap else {}

    @staticmethod
    def _metric_diff(base: dict, target: dict) -> list[dict]:
        diffs = []
        for group, field, label in VersionCompareService.METRIC_FIELDS:
            b = (base.get(group) or {}).get(field, 0)
            t = (target.get(group) or {}).get(field, 0)
            if isinstance(b, (int, float)) and isinstance(t, (int, float)):
                delta = round(t - b, 4)
                pct = round(delta / b * 100, 1) if b else None
                diffs.append({
                    "group": group, "field": field, "label": label,
                    "base": b, "target": t, "delta": delta,
                    "pct": pct,
                    "changed": abs(delta) > 1e-9,
                })
        return diffs

    @staticmethod
    def _text_diff(base_md: str, target_md: str) -> dict:
        import difflib

        def _split_sections(md: str) -> dict[str, list[str]]:
            """按 '## ' 章节切分，返回 章节名 → 行列表"""
            sections: dict[str, list[str]] = {}
            current = "_header"
            for line in (md or "").splitlines():
                if line.startswith("## "):
                    current = line[3:].strip()
                    sections.setdefault(current, [])
                else:
                    sections.setdefault(current, []).append(line)
            return sections

        base_secs = _split_sections(base_md)
        target_secs = _split_sections(target_md)
        result = []
        for name in sorted(set(base_secs) | set(target_secs)):
            b_lines, t_lines = base_secs.get(name, []), target_secs.get(name, [])
            sm = difflib.SequenceMatcher(None, b_lines, t_lines)
            added = removed = changed = 0
            samples = []
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "insert":
                    added += j2 - j1
                    samples.append(("+", t_lines[j1:j2][0][:80]))
                elif tag == "delete":
                    removed += i2 - i1
                    samples.append(("-", b_lines[i1:i2][0][:80]))
                elif tag == "replace":
                    changed += max(i2 - i1, j2 - j1)
                    samples.append(("~", t_lines[j1:j2][0][:80] if j2 > j1 else b_lines[i1:i2][0][:80]))
            if added or removed or changed:
                result.append({
                    "section": name,
                    "added": added, "removed": removed, "changed": changed,
                    "samples": samples[:5],
                })
        return {"sections": result, "totalAdded": sum(s["added"] for s in result),
                "totalRemoved": sum(s["removed"] for s in result),
                "totalChanged": sum(s["changed"] for s in result)}
