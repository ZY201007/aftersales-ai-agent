"""工具白名单与工具结果测试。"""
import pytest

from app.tools import ALLOWED_TOOLS, ToolNotAllowedError, ToolRegistry


def test_whitelist_content():
    assert ALLOWED_TOOLS == {"query_order", "query_logistics", "check_refund_policy"}
    # 退款审批绝不能作为工具暴露给 Agent
    assert "approve_refund" not in ALLOWED_TOOLS


def test_allowed_tool_returns_source_id():
    tools = ToolRegistry()
    result = tools.call("query_order", order_id="ORD1001")
    assert result.success is True
    assert result.source_id == "order:ORD1001"
    assert result.data["order_id"] == "ORD1001"


def test_missing_order_fails():
    tools = ToolRegistry()
    assert tools.call("query_order", order_id="NOT_EXIST").success is False
    assert tools.call("query_logistics", order_id=None).success is False


def test_non_allowlisted_tool_rejected():
    tools = ToolRegistry()
    with pytest.raises(ToolNotAllowedError):
        tools.call("delete_order", order_id="ORD1001")


def test_list_tools():
    names = [item["name"] for item in ToolRegistry().list_tools()]
    assert names == sorted(ALLOWED_TOOLS)
