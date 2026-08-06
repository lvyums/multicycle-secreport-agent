"""本地推送策略 — 归档到本地（V1.1 默认交付渠道）"""

from typing import Optional

from capability.push.push_strategy import PushStrategy, PushResult
from common.logger.logger import LogManager

logger = LogManager.get_logger()


class LocalPushStrategy(PushStrategy):
    """本地归档：确认文件存在并记录归档路径"""

    channel = "local"

    def push(self, version_info: dict, context: Optional[dict] = None) -> PushResult:
        from infra.storage import file_store
        file_path = version_info.get("file_path") or ""
        if file_path and file_store.file_exists(file_path):
            return PushResult(
                success=True, channel=self.channel,
                detail=f"已归档: {file_path}",
                extra={"path": file_path},
            )
        # 无文件时用 content_md 落盘
        content = version_info.get("content_md") or ""
        if content:
            from infra.storage import file_store as fs
            from config.settings import settings
            import os
            path = fs.build_report_path(version_info.get("cycle", "unknown"),
                                        version_info.get("version_no", 1), "md")
            fs.save_file(content, path)
            return PushResult(success=True, channel=self.channel,
                              detail=f"已归档(实时落盘): {path}", extra={"path": path})
        return PushResult(success=False, channel=self.channel, detail="版本无内容可推送")
