"""审核状态机测试 — 合法/非法流转 + 审计日志"""
import sys
sys.path.insert(0, ".")

import pytest

from app.services.audit_service import AuditService, TRANSITIONS, VALID_ACTIONS
from common.exception.exception import BusinessError


class _FakeVersion:
    def __init__(self, status="DRAFT"):
        self.id = 1
        self.status = status
        self.remark = ""


def test_valid_transition_draft_to_reviewing():
    v = _FakeVersion("DRAFT")
    assert AuditService.transition(v, "submit") == "REVIEWING"
    assert v.status == "REVIEWING"


def test_valid_transition_reviewing_approve_reject():
    v = _FakeVersion("REVIEWING")
    assert AuditService.transition(v, "approve") == "APPROVED"
    v2 = _FakeVersion("REVIEWING")
    assert AuditService.transition(v2, "reject") == "DRAFT"


def test_approved_archive_only():
    v = _FakeVersion("APPROVED")
    assert AuditService.transition(v, "archive") == "ARCHIVED"
    v2 = _FakeVersion("APPROVED")
    with pytest.raises(BusinessError):
        AuditService.transition(v2, "reject")


def test_draft_cannot_approve_directly():
    v = _FakeVersion("DRAFT")
    with pytest.raises(BusinessError):
        AuditService.transition(v, "approve")


def test_unknown_action_rejected():
    v = _FakeVersion("DRAFT")
    with pytest.raises(BusinessError):
        AuditService.transition(v, "delete")


def test_remark_recorded_on_transition():
    v = _FakeVersion("DRAFT")
    AuditService.transition(v, "submit", operator="zhangwx", remark="请审核")
    assert v.remark == "请审核"


def test_transition_table_consistency():
    # 所有动作必须出现在流转表中
    assert VALID_ACTIONS == {"submit", "approve", "reject", "archive"}
    assert TRANSITIONS["DRAFT"] == {"submit": "REVIEWING"}
    assert TRANSITIONS["REVIEWING"] == {"approve": "APPROVED", "reject": "DRAFT"}
    assert TRANSITIONS["APPROVED"] == {"archive": "ARCHIVED"}
