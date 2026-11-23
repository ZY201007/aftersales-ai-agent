"""引用溯源与反幻觉校验测试。"""
from app.citations import build_citations, extract_source_ids, verify_citations
from app.schemas import ToolResult


def _results():
    return [
        ToolResult(
            tool_name="query_order",
            source_id="order:ORD1001",
            data={"order_id": "ORD1001", "item": "耳机"},
        ),
        ToolResult(
            tool_name="check_refund_policy",
            source_id="policy:RETURN-7D",
            data={"window_days": 7},
        ),
    ]


def test_extract_source_ids():
    text = "订单信息【来源:order:ORD1001】符合政策【来源:policy:RETURN-7D】"
    assert extract_source_ids(text) == ["order:ORD1001", "policy:RETURN-7D"]


def test_build_citations():
    text = "订单信息【来源:order:ORD1001】"
    citations = build_citations(text, _results())
    assert len(citations) == 1
    assert citations[0].source_id == "order:ORD1001"
    assert "ORD1001" in citations[0].snippet


def test_verify_ok():
    text = "订单信息【来源:order:ORD1001】"
    citations = build_citations(text, _results())
    ok, reason = verify_citations(text, citations, _results())
    assert ok is True and reason == "ok"


def test_verify_rejects_unknown_source():
    text = "订单信息【来源:g fabricated:123】"
    citations = build_citations(text, _results())
    ok, _ = verify_citations(text, citations, _results())
    assert ok is False


def test_verify_rejects_answer_without_citation():
    text = "订单肯定没问题，您放心。"  # 无来源标记 -> 幻觉嫌疑
    ok, _ = verify_citations(text, [], _results())
    assert ok is False


def test_verify_rejects_empty_tool_results():
    ok, _ = verify_citations("随便说说", [], [])
    assert ok is False
