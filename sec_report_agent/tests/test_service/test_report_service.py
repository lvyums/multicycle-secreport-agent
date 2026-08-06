"""服务层测试 — 报告生成 pipeline（mock 数据源 → 状态机）"""
import sys, os
sys.path.insert(0, ".")

import pytest

from capability.adapter.mock_data_gen import ensure_mock_files
from app.services.report_service import ReportService


@pytest.mark.asyncio
async def test_generate_monthly_success():
    ensure_mock_files()
    from infra.db.session import init_db
    init_db()
    result = await ReportService.generate("MONTHLY", "2026-07-01 00:00:00", "2026-08-01 00:00:00", trigger_type="TEST")
    assert result["status"] in ("SUCCESS", "EMPTY", "PARTIAL")
    assert result["task_id"] > 0
    # 幂等命中时只有精简字段；非复用才有完整结果
    if not result.get("reused") and result["status"] == "SUCCESS":
        assert result["event_count"] > 0
        assert result["version_id"] > 0


@pytest.mark.asyncio
async def test_generate_rerun_idempotent():
    ensure_mock_files()
    from infra.db.session import init_db
    init_db()
    r1 = await ReportService.generate("MONTHLY", "2026-07-01 00:00:00", "2026-08-01 00:00:00", trigger_type="TEST")
    r2 = await ReportService.generate("MONTHLY", "2026-07-01 00:00:00", "2026-08-01 00:00:00", trigger_type="TEST")
    # 幂等：同窗口复用任务
    assert r2["reused"] is True or r1["reused"] is True
