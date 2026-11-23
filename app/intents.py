"""意图分类：退货 / 查物流 / 退款。

线上由 LLM 完成分类；MockLLM 与离线评测使用本模块的确定性关键词分类器。
优先级设计为 退款 > 退货 > 物流：涉及资金的操作一律走更保守的人工审批链路。
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

from .schemas import IntentEnum

INTENT_KEYWORDS: Dict[IntentEnum, Tuple[str, ...]] = {
    IntentEnum.REFUND: (
        "退款", "退钱", "返款", "退回钱", "退还", "把钱退", "退给我", "退回来",
        "退回款项", "refund",
    ),
    IntentEnum.RETURN: (
        "退货", "退回", "寄回", "退换", "换货", "退货退款", "七天无理由", "return",
    ),
    IntentEnum.LOGISTICS: (
        "物流", "快递", "发货", "运单", "单号", "到哪", "什么时候到", "运输",
        "派送", "查件", "签收", "轨迹", "物流信息", "shipping", "logistics",
    ),
}

# 意图优先级：退款 > 退货 > 物流（资金操作优先保守处理）
INTENT_PRIORITY: Tuple[IntentEnum, ...] = (
    IntentEnum.REFUND,
    IntentEnum.RETURN,
    IntentEnum.LOGISTICS,
)

_ORDER_ID_PATTERNS = (
    re.compile(r"订单号?\s*[:：#]?\s*(ORD\d{3,})", re.IGNORECASE),
    re.compile(r"\b(ORD\d{3,})\b", re.IGNORECASE),
)


def classify_intent(text: str) -> Tuple[IntentEnum, float]:
    """返回 (意图, 置信度)。完全确定性，便于测试与复现。"""
    normalized = (text or "").lower()
    scores = {
        intent: sum(1 for kw in keywords if kw in normalized)
        for intent, keywords in INTENT_KEYWORDS.items()
    }
    for intent in INTENT_PRIORITY:
        if scores[intent] > 0:
            confidence = min(1.0, 0.65 + 0.15 * (scores[intent] - 1))
            return intent, confidence
    return IntentEnum.UNKNOWN, 0.0


def extract_order_id(text: str) -> str | None:
    """从文本中抽取 ORD 开头的订单号；抽不到返回 None。"""
    normalized = text or ""
    for pattern in _ORDER_ID_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return match.group(1).upper()
    return None
