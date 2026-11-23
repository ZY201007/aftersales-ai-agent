"""Pydantic 数据模型：贯穿 API、Agent、工具与离线评测。

所有跨模块传递的数据结构都集中在这里定义，避免各处重复造轮子。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IntentEnum(str, Enum):
    """三类高频售后意图 + 兜底未知意图。"""

    RETURN = "return"          # 退货
    LOGISTICS = "logistics"    # 查物流
    REFUND = "refund"          # 退款
    UNKNOWN = "unknown"        # 无法识别


class TierEnum(str, Enum):
    """分级 Agent 链路的三个层级。"""

    AUTO_REPLY = "auto_reply"            # 查询类：工具可核验，自动回复
    HUMAN_APPROVAL = "human_approval"    # 退款类：资金操作，必须人工审批
    HUMAN_FALLBACK = "human_fallback"    # 反幻觉兜底：无可靠来源，转人工


class CustomerMessage(BaseModel):
    """用户咨询输入。"""

    text: str = Field(..., description="用户原始咨询文本")
    order_id: Optional[str] = Field(None, description="可选：用户显式提供的订单号")
    session_id: Optional[str] = Field(None, description="可选：会话 ID，便于日志追踪")


class Citation(BaseModel):
    """一条答案引用：指向工具结果 ID 或政策文档 ID。"""

    source_id: str = Field(..., description="来源标识，如 order:ORD1001 / policy:REFUND-7D")
    snippet: str = Field(..., description="来源内容摘要，便于人工复核")


class ToolResult(BaseModel):
    """工具调用结果。success=False 表示该工具无法为答案提供依据。"""

    tool_name: str
    source_id: str
    data: Dict[str, Any]
    success: bool = True


class ApprovalStatus(str, Enum):
    """人工审批工单状态。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalTicket(BaseModel):
    """退款人工审批工单。"""

    id: str
    order_id: Optional[str]
    intent: IntentEnum
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str
    resolved_at: Optional[str] = None
    answer: Optional[str] = None


class AgentResponse(BaseModel):
    """Agent 处理后的完整响应，也是离线评测记录的最小单元。"""

    session_id: str
    intent: IntentEnum
    intent_confidence: float = 0.0
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    tool_calls: List[str] = Field(default_factory=list)
    tier: TierEnum
    auto_resolved: bool = False
    escalated: bool = False
    # 错误升级：本可自动解决却被转人工（用于计算净解决率的扣减项）
    false_escalation: bool = False
    escalate_reason: Optional[str] = None
    approval_id: Optional[str] = None
    token_in: int = 0
    token_out: int = 0
    # 是否使用了「模型能力模拟」（仅离线评测开启，线上恒为 False）
    simulated_capability_used: bool = False
