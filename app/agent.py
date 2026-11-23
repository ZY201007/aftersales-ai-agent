"""分级 Agent 链路：意图识别 -> 白名单工具调用 -> 带引用回答 -> 分级处置。

三条层级：
- return / logistics 且回答可被工具结果支撑 -> 自动回复（auto_reply）
- refund -> 生成 pending 审批工单，绝不自动批准（human_approval）
- 无可靠来源或能力不足 -> 拒绝作答并转人工（human_fallback）
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .approval import ApprovalQueue
from .citations import build_citations, verify_citations
from .intents import extract_order_id
from .llm import LLMClient
from .schemas import (
    AgentResponse,
    CustomerMessage,
    IntentEnum,
    TierEnum,
    ToolResult,
)
from .tools import ToolRegistry

# 每个意图允许调用的工具（全部来自白名单），顺序即调用顺序
TOOL_PLAN: Dict[IntentEnum, Tuple[Tuple[str, Dict], ...]] = {
    IntentEnum.RETURN: (
        ("query_order", {}),
        ("check_refund_policy", {"policy_type": "return"}),
    ),
    IntentEnum.LOGISTICS: (
        ("query_order", {}),
        ("query_logistics", {}),
    ),
    IntentEnum.REFUND: (
        ("query_order", {}),
        ("check_refund_policy", {"policy_type": "refund"}),
    ),
    IntentEnum.UNKNOWN: (),
}


@dataclass
class AgentConfig:
    """Agent 版本配置。"""

    version: str = "v2"
    concise_prompt: bool = True
    # 仅离线评测使用：模拟不同代次模型的能力阈值
    simulated_capability: float | None = None


VERSION_PRESETS: Dict[str, AgentConfig] = {
    "v1": AgentConfig(version="v1", concise_prompt=False),
    "v2": AgentConfig(version="v2", concise_prompt=True),
}


class AfterSalesAgent:
    """售后 Agent：编排分类、工具、引用校验与人工审批。"""

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        approvals: ApprovalQueue,
        config: AgentConfig | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.approvals = approvals
        self.config = config or AgentConfig()

    def _run_tools(
        self, intent: IntentEnum, order_id: str | None
    ) -> Tuple[List[str], List[ToolResult]]:
        """按意图调用白名单工具；工具名与参数均在代码中静态定义。"""
        calls: List[str] = []
        results: List[ToolResult] = []
        for tool_name, extra in TOOL_PLAN.get(intent, ()):
            if not self.tools.is_allowed(tool_name):
                continue  # 双重保险：白名单外的工具永不执行
            calls.append(tool_name)
            results.append(self.tools.call(tool_name, order_id=order_id, **extra))
        return calls, results

    def handle(
        self, message: CustomerMessage, difficulty: float | None = None
    ) -> AgentResponse:
        """处理一条用户咨询。

        difficulty 仅用于离线评测的模型能力模拟；线上调用不传该参数。
        """
        order_id = message.order_id or extract_order_id(message.text)
        intent, confidence = self.llm.classify(message.text)
        tool_calls, tool_results = self._run_tools(intent, order_id)
        answer = self.llm.answer(
            intent,
            tool_results,
            concise=self.config.concise_prompt,
            order_id=order_id,
        )
        citations = build_citations(answer.text, tool_results)
        valid, reason = verify_citations(answer.text, citations, tool_results)

        common = dict(
            session_id=message.session_id or uuid.uuid4().hex[:12],
            intent=intent,
            intent_confidence=confidence,
            tool_calls=tool_calls,
            token_in=answer.token_in,
            token_out=answer.token_out,
        )

        # 层级二：退款 -> 必须人工审批，创建 pending 工单
        if intent == IntentEnum.REFUND:
            ticket = self.approvals.create(
                order_id=order_id,
                intent=intent,
                reason="退款涉及资金操作，须人工审批后方可执行",
                answer=answer.text,
            )
            final_answer = (
                f"{answer.text}\n[审批工单 {ticket.id} 已创建，状态：pending，"
                f"需人工审核后才能退款]"
            )
            return AgentResponse(
                **common,
                answer=final_answer,
                citations=citations,
                tier=TierEnum.HUMAN_APPROVAL,
                auto_resolved=False,
                escalated=True,
                escalate_reason="refund_requires_human_approval",
                approval_id=ticket.id,
            )

        # 层级三：反幻觉校验失败 -> 拒绝作答，转人工兜底
        if not valid:
            return AgentResponse(
                **common,
                answer=answer.text,
                citations=citations,
                tier=TierEnum.HUMAN_FALLBACK,
                auto_resolved=False,
                escalated=True,
                escalate_reason=f"citation_check_failed: {reason}",
            )

        # 离线能力模拟：能力不足导致本可自动解决的工单被错误转人工
        if (
            self.config.simulated_capability is not None
            and difficulty is not None
            and difficulty > self.config.simulated_capability
        ):
            return AgentResponse(
                **common,
                answer="（模型能力模拟）该工单本可自动解决，但当前版本未能可靠作答，已转人工。",
                citations=[],
                tier=TierEnum.HUMAN_FALLBACK,
                auto_resolved=False,
                escalated=True,
                false_escalation=True,
                escalate_reason="simulated_model_capability_insufficient",
                simulated_capability_used=True,
            )

        # 层级一：有来源支撑 -> 自动回复闭环
        return AgentResponse(
            **common,
            answer=answer.text,
            citations=citations,
            tier=TierEnum.AUTO_REPLY,
            auto_resolved=True,
            escalated=False,
        )
