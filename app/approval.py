"""退款人工审批队列（分级链路的「人工审批」层）。

退款涉及资金，Agent 永远不自动批准；只会创建 pending 工单，
由人工调用 decide(approve/reject) 做出最终决定。
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .schemas import ApprovalStatus, ApprovalTicket, IntentEnum


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApprovalQueue:
    """线程安全的内存审批队列（演示用，生产可替换为数据库实现）。"""

    def __init__(self) -> None:
        self._items: Dict[str, ApprovalTicket] = {}
        self._lock = threading.Lock()

    def create(
        self,
        order_id: Optional[str],
        intent: IntentEnum,
        reason: str,
        answer: Optional[str] = None,
    ) -> ApprovalTicket:
        ticket = ApprovalTicket(
            id=f"AP-{uuid.uuid4().hex[:8].upper()}",
            order_id=order_id,
            intent=intent,
            reason=reason,
            status=ApprovalStatus.PENDING,
            created_at=_now(),
            answer=answer,
        )
        with self._lock:
            self._items[ticket.id] = ticket
        return ticket

    def get(self, ticket_id: str) -> Optional[ApprovalTicket]:
        with self._lock:
            return self._items.get(ticket_id)

    def list(self, status: Optional[ApprovalStatus] = None) -> List[ApprovalTicket]:
        with self._lock:
            items = list(self._items.values())
        if status is not None:
            items = [t for t in items if t.status == status]
        return sorted(items, key=lambda t: t.created_at)

    def decide(
        self, ticket_id: str, status: ApprovalStatus
    ) -> Optional[ApprovalTicket]:
        """仅允许从 pending 流转到 approved / rejected。"""
        if status not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
            raise ValueError("终态只能是 approved 或 rejected")
        with self._lock:
            ticket = self._items.get(ticket_id)
            if ticket is None:
                return None
            if ticket.status != ApprovalStatus.PENDING:
                return ticket
            ticket.status = status
            ticket.resolved_at = _now()
            return ticket
