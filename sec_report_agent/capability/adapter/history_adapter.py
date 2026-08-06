"""历史报告源适配器 — 从 MetricSnapshot 回读上一周期指标（环比数据，V1.2）

返回一条特殊事件（event_type=history_metric），pipeline 聚合后提取为 trend.compare。
"""

from typing import Optional

from capability.adapter.adapter_base import DataSourceAdapter
from common.logger.logger import LogManager

logger = LogManager.get_logger()


class HistoryAdapter(DataSourceAdapter):
    """历史报告适配器（读取上一周期指标快照）"""

    type = "HISTORY"

    def validate_config(self) -> list[str]:
        # 历史源无需文件配置（数据来自 MetricSnapshot 表）
        return []

    def fetch(self, window_start: str, window_end: str, task_id: int = 0) -> list[dict]:
        """查找同周期上一窗口的指标快照，返回历史指标事件"""
        from infra.db.session import SessionLocal
        from infra.db.repositories import MetricSnapshotRepo

        cycle = (self.config.config_json or {}).get("cycle", "")
        db = SessionLocal()
        try:
            prev = MetricSnapshotRepo.find_prev_snapshot(db, cycle, window_start, window_end)
        finally:
            db.close()

        if not prev:
            logger.info(f"[HISTORY] {self.name} 无上一周期快照（{window_start}~{window_end}），跳过环比")
            return []
        metrics = prev.metrics_json or {}
        logger.info(f"[HISTORY] {self.name} 取到上一周期指标: "
                    f"alert.total={metrics.get('alert', {}).get('total', 0)}")
        return [{
            "source_type": "HISTORY",
            "source_name": self.name,
            "receive_time": window_end,
            "raw_content": "history metric snapshot",
            "status": "OK",
            "extra": {
                "event_type": "history_metric",
                "risk_hint": "INFO",
                "prev_metrics": metrics,
                "prev_window": f"{prev.window_start}~{prev.window_end}",
            },
        }]
