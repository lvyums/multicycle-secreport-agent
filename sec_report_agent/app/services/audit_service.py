"""审核服务 — 报告版本状态机：DRAFT → REVIEWING → APPROVED / REJECTED(→DRAFT)

状态变更强制落 AuditLog（操作者/动作/目标/详情）。
"""

from common.logger.logger import LogManager

logger = LogManager.get_logger()

# 合法流转表
TRANSITIONS = {
    "DRAFT": {"submit": "REVIEWING"},        # 提交审核
    "REVIEWING": {"approve": "APPROVED", "reject": "DRAFT"},  # 终审通过 / 驳回回初稿
    "APPROVED": {"archive": "ARCHIVED"},     # 归档（终审通过后）
}

VALID_ACTIONS = {"submit", "approve", "reject", "archive"}


class AuditService:
    """版本审核流转服务"""

    @staticmethod
    def transition(version, action: str, operator: str = "system", remark: str = "") -> str:
        """执行状态流转，返回新状态；非法流转抛 ValueError"""
        from common.exception.exception import BusinessError

        if action not in VALID_ACTIONS:
            raise BusinessError(f"非法审核动作: {action}，可用: {sorted(VALID_ACTIONS)}", code=400)

        allowed = TRANSITIONS.get(version.status, {})
        if action not in allowed:
            raise BusinessError(
                f"状态流转不允许: {version.status} → {action}（当前仅支持: {list(allowed.keys())}）",
                code=400,
            )

        new_status = allowed[action]
        old_status = version.status
        version.status = new_status
        if remark:
            version.remark = remark[:200]
        logger.info(f"[AUDIT] 版本#{version.id} {old_status} → {new_status} by {operator} ({action})")
        return new_status

    @staticmethod
    def log_audit(db, version_id: int, action: str, operator: str,
                  detail: str = "", trace_id: str = "") -> None:
        """落审计日志（强制）"""
        from infra.db.repositories import AuditLogRepo
        AuditLogRepo.add(db, operator=operator, action=f"VERSION_{action}",
                         target_type="ReportVersion", target_id=version_id,
                         detail=detail[:400], trace_id=trace_id)
