"""工具注册表与白名单（anti-hallucination 的第一道闸门）。

设计要点：
1. Agent 只能调用 ALLOWED_TOOLS 中登记的工具，未登记的工具一律拒绝；
2. 每个工具结果都带 source_id，供回答引用与溯源；
3. 「退款审批」不是工具——它必须进入人工审批队列，绝不在工具层自动执行。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from .schemas import ToolResult

# 工具白名单：新增工具必须显式加入此处，Agent 无法自行发现其它能力
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {"query_order", "query_logistics", "check_refund_policy"}
)

_ITEMS = (
    "无线蓝牙耳机", "纯棉四件套", "智能护眼台灯", "运动保温杯",
    "儿童积木套装", "家用咖啡机", "手机支架", "瑜伽垫",
)
_CARRIERS = ("顺丰速运", "中通快递", "京东物流", "圆通速递")
_STATUSES = ("已签收", "运输中", "派送中", "已发货")


def _build_mock_orders() -> Dict[str, Dict[str, Any]]:
    """构造 60 条确定性的演示订单，无需任何外部数据库。"""
    orders: Dict[str, Dict[str, Any]] = {}
    for i in range(1, 61):
        order_id = f"ORD{1000 + i}"
        orders[order_id] = {
            "order_id": order_id,
            "item": _ITEMS[i % len(_ITEMS)],
            "amount": round(59 + (i * 17) % 400 + 0.9, 2),
            "status": _STATUSES[i % len(_STATUSES)],
            "days_since_purchase": 1 + i % 20,
            "carrier": _CARRIERS[i % len(_CARRIERS)],
            "tracking_no": f"SF{20260000 + i}",
            "logistics_status": _STATUSES[(i + 1) % len(_STATUSES)],
            "eta": f"2026-11-{20 + (i % 8):02d}",
            "return_window_days": 7,
            "refund_window_days": 7,
        }
    return orders


MOCK_ORDERS: Dict[str, Dict[str, Any]] = _build_mock_orders()


class ToolNotAllowedError(PermissionError):
    """调用不在白名单中的工具时抛出。"""


class ToolRegistry:
    """工具注册表：所有调用都经过白名单校验。"""

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable[..., ToolResult]] = {
            "query_order": self.query_order,
            "query_logistics": self.query_logistics,
            "check_refund_policy": self.check_refund_policy,
        }

    @staticmethod
    def is_allowed(name: str) -> bool:
        return name in ALLOWED_TOOLS

    def list_tools(self) -> List[Dict[str, str]]:
        """列出可用工具（供 API 文档 / 前端展示）。"""
        descriptions = {
            "query_order": "查询订单状态、商品、金额、购买时长",
            "query_logistics": "查询承运商、运单号、物流轨迹与预计送达时间",
            "check_refund_policy": "查询退货 / 退款政策窗口",
        }
        return [
            {"name": name, "description": descriptions[name]}
            for name in sorted(ALLOWED_TOOLS)
        ]

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        """统一调用入口：先过白名单，再分发。"""
        if not self.is_allowed(name):
            raise ToolNotAllowedError(f"工具 {name!r} 不在白名单中，拒绝调用")
        handler = self._handlers[name]
        return handler(**kwargs)

    # ---- 具体工具 ----
    @staticmethod
    def query_order(order_id: str | None = None) -> ToolResult:
        source_id = f"order:{order_id}"
        order = MOCK_ORDERS.get(order_id or "")
        if order is None:
            return ToolResult(
                tool_name="query_order",
                source_id=source_id,
                data={"error": "订单不存在或未提供订单号"},
                success=False,
            )
        return ToolResult(tool_name="query_order", source_id=source_id, data=dict(order))

    @staticmethod
    def query_logistics(order_id: str | None = None) -> ToolResult:
        source_id = f"logistics:{order_id}"
        order = MOCK_ORDERS.get(order_id or "")
        if order is None:
            return ToolResult(
                tool_name="query_logistics",
                source_id=source_id,
                data={"error": "订单不存在，无法查询物流"},
                success=False,
            )
        data = {
            "order_id": order_id,
            "carrier": order["carrier"],
            "tracking_no": order["tracking_no"],
            "logistics_status": order["logistics_status"],
            "eta": order["eta"],
        }
        return ToolResult(tool_name="query_logistics", source_id=source_id, data=data)

    @staticmethod
    def check_refund_policy(
        order_id: str | None = None, policy_type: str = "refund"
    ) -> ToolResult:
        prefix = "RETURN" if policy_type == "return" else "REFUND"
        source_id = f"policy:{prefix}-7D"
        if order_id not in MOCK_ORDERS:
            return ToolResult(
                tool_name="check_refund_policy",
                source_id=source_id,
                data={"error": "订单不存在，政策无法套用"},
                success=False,
            )
        rule = (
            "签收后 7 天内可申请无理由退货，商品需保持完好"
            if policy_type == "return"
            else "签收后 7 天内可申请退款；涉及资金的操作须经人工审核"
        )
        return ToolResult(
            tool_name="check_refund_policy",
            source_id=source_id,
            data={
                "order_id": order_id,
                "policy_type": policy_type,
                "window_days": 7,
                "rule": rule,
            },
        )
