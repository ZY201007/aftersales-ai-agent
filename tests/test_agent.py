"""分级 Agent 链路端到端测试。"""
from app.agent import AfterSalesAgent, AgentConfig, VERSION_PRESETS
from app.approval import ApprovalQueue
from app.llm import MockLLM
from app.schemas import ApprovalStatus, CustomerMessage, TierEnum
from app.tools import ToolRegistry


def make_agent(config=None):
    return AfterSalesAgent(MockLLM(), ToolRegistry(), ApprovalQueue(), config)


def test_return_auto_reply():
    response = make_agent().handle(CustomerMessage(text="订单 ORD1001 想退货"))
    assert response.intent.value == "return"
    assert response.tier == TierEnum.AUTO_REPLY
    assert response.auto_resolved is True
    assert response.escalated is False
    assert len(response.citations) >= 2
    assert response.tool_calls == ["query_order", "check_refund_policy"]


def test_logistics_auto_reply():
    response = make_agent().handle(CustomerMessage(text="查一下 ORD1002 的物流"))
    assert response.tier == TierEnum.AUTO_REPLY
    assert response.auto_resolved is True
    assert response.tool_calls == ["query_order", "query_logistics"]
    assert any(c.source_id.startswith("logistics:") for c in response.citations)


def test_refund_goes_to_human_approval():
    queue = ApprovalQueue()
    agent = AfterSalesAgent(MockLLM(), ToolRegistry(), queue)
    response = agent.handle(CustomerMessage(text="订单 ORD1003 我要退款"))

    assert response.tier == TierEnum.HUMAN_APPROVAL
    assert response.auto_resolved is False
    assert response.escalated is True
    assert response.approval_id is not None
    ticket = queue.get(response.approval_id)
    assert ticket.status == ApprovalStatus.PENDING  # 绝不自动批准


def test_no_order_id_falls_back_to_human():
    response = make_agent().handle(CustomerMessage(text="商品不想要了想退货，单号没记住"))
    assert response.tier == TierEnum.HUMAN_FALLBACK
    assert response.escalated is True
    assert response.auto_resolved is False
    assert response.citations == []


def test_capability_simulation():
    config = AgentConfig(simulated_capability=0.5)
    agent = make_agent(config)
    failed = agent.handle(
        CustomerMessage(text="订单 ORD1004 想退货"), difficulty=0.9
    )
    assert failed.false_escalation is True
    assert failed.escalated is True
    assert failed.simulated_capability_used is True

    passed = agent.handle(
        CustomerMessage(text="订单 ORD1004 想退货"), difficulty=0.1
    )
    assert passed.auto_resolved is True
    assert passed.false_escalation is False


def test_token_cost_diff_between_versions():
    msg = CustomerMessage(text="订单 ORD1005 想退货")
    v1 = make_agent(VERSION_PRESETS["v1"]).handle(msg)
    v2 = make_agent(VERSION_PRESETS["v2"]).handle(msg)
    assert v1.token_in > v2.token_in
    assert v1.token_out > v2.token_out
