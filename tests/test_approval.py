"""人工审批队列测试。"""
from app.approval import ApprovalQueue
from app.schemas import ApprovalStatus, IntentEnum


def test_approval_lifecycle():
    queue = ApprovalQueue()
    ticket = queue.create("ORD1001", IntentEnum.REFUND, "退款需人工审核")
    assert ticket.status == ApprovalStatus.PENDING

    decided = queue.decide(ticket.id, ApprovalStatus.APPROVED)
    assert decided.status == ApprovalStatus.APPROVED
    assert decided.resolved_at is not None

    # 终态不可再次变更
    again = queue.decide(ticket.id, ApprovalStatus.REJECTED)
    assert again.status == ApprovalStatus.APPROVED


def test_filter_and_missing():
    queue = ApprovalQueue()
    queue.create("ORD1002", IntentEnum.REFUND, "原因1")
    queue.create("ORD1003", IntentEnum.REFUND, "原因2")
    assert len(queue.list(ApprovalStatus.PENDING)) == 2
    assert queue.get("NOT_EXIST") is None
    assert queue.decide("NOT_EXIST", ApprovalStatus.APPROVED) is None


def test_invalid_terminal_state():
    import pytest

    queue = ApprovalQueue()
    with pytest.raises(ValueError):
        queue.decide("AP-XXX", ApprovalStatus.PENDING)
