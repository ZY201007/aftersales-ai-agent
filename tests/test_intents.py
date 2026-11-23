"""意图分类测试。"""
from app.intents import classify_intent, extract_order_id
from app.schemas import IntentEnum


def test_three_intents():
    assert classify_intent("订单 ORD1001 想退货")[0] == IntentEnum.RETURN
    assert classify_intent("查一下 ORD1001 的物流")[0] == IntentEnum.LOGISTICS
    assert classify_intent("ORD1001 我要退款")[0] == IntentEnum.REFUND


def test_refund_priority_over_return():
    # 涉及资金优先按退款处理（走更保守的人工审批链路）
    assert classify_intent("订单 ORD1001 退货退款")[0] == IntentEnum.REFUND


def test_unknown():
    intent, confidence = classify_intent("今天天气怎么样")
    assert intent == IntentEnum.UNKNOWN
    assert confidence == 0.0


def test_extract_order_id():
    assert extract_order_id("订单号：ORD1001 想退货") == "ORD1001"
    assert extract_order_id("我的快递 ord1234 到哪了") == "ORD1234"
    assert extract_order_id("商品不想要了") is None
