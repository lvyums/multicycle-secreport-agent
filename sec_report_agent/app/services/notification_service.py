"""站内通知服务（V2.8）— 四类消息统一入口，异常不阻断业务

埋点：REPORT_READY(报告生成完成→admin) / PUSH_FAIL(推送失败→admin)
      ALERT(告警触发→admin) / REVIEW_RESULT(审核结果→版本创建人)
"""

from common.logger.logger import LogManager

logger = LogManager.get_logger()


class NotificationService:
    """通知写入（内部捕获异常，失败仅记日志不影响主链路）"""

    @staticmethod
    def notify(ntype: str, title: str, content: str = "",
               level: str = "info", target_user: str = "",
               task_id: int = 0, version_id: int = 0) -> None:
        try:
            from infra.db.session import SessionLocal
            from infra.db.repositories import NotificationRepo
            db = SessionLocal()
            try:
                NotificationRepo.add(
                    db, ntype=ntype, title=title[:250], content=content[:2000],
                    level=level, target_user=target_user,
                    task_id=task_id, version_id=version_id,
                )
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001 通知失败不阻断业务
            logger.warning(f"[NOTIFY] {ntype} 写入失败: {e}")

    # ── 便捷封装 ──

    @classmethod
    def report_ready(cls, cycle: str, window_start: str, window_end: str,
                     task_id: int, version_id: int) -> None:
        cls.notify(
            "REPORT_READY",
            f"{cycle} 报告已生成（{window_start[:10]}~{window_end[:10]}）",
            f"任务 #{task_id} 生成 {cycle} 周期报告，待审核。",
            level="info", target_user="admin",
            task_id=task_id, version_id=version_id,
        )

    @classmethod
    def push_fail(cls, cycle: str, channel: str, version_id: int,
                  detail: str) -> None:
        cls.notify(
            "PUSH_FAIL",
            f"推送失败：{channel}",
            f"{cycle} 报告 #{version_id} 推送 {channel} 渠道失败：{detail[:300]}",
            level="error", target_user="admin",
            version_id=version_id,
        )

    @classmethod
    def alert_fired(cls, rule_key: str, name: str, desc: str) -> None:
        cls.notify(
            "ALERT",
            f"告警触发：{name}",
            f"{desc}",
            level="warning", target_user="admin",
        )

    @classmethod
    def review_result(cls, version_id: int, action: str,
                      operator: str, target_user: str, remark: str = "") -> None:
        act_label = {"approve": "审核通过", "reject": "已驳回",
                     "archive": "已归档"}.get(action, action)
        cls.notify(
            "REVIEW_RESULT",
            f"报告{act_label}",
            f"报告 #{version_id} 被 {operator} {act_label}。{remark}",
            level="info", target_user=target_user,
            version_id=version_id,
        )

    @classmethod
    def empty_report(cls, cycle: str, window_start: str, window_end: str,
                     task_id: int, version_id: int, reason: str = "") -> None:
        cls.notify(
            "ALERT",
            f"EMPTY 报告：{cycle} 无安全事件",
            f"{cycle} {window_start[:10]}~{window_end[:10]} 无告警/漏洞数据"
            f"，已生成占位报告 #{version_id}。{reason}",
            level="warning", target_user="admin",
            task_id=task_id, version_id=version_id,
        )
