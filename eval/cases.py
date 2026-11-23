"""200 条离线评测集的生成器。

构成（固定 200 条，固定种子，完全可复现）：
  - 30 条退款：应进入人工审批（本就不能自动解决）
  - 10 条缺少订单号：反幻觉校验应拦截并转人工
  - 160 条退货/查物流（带订单号）：可自动解决，difficulty 用于模拟模型能力

难度 difficulty = (i + 0.5) / 160（i 为可自动解决样本序号），均匀分布。
配合 fixtures.CAPABILITY_BY_VERSION：
  v1 能力 0.65   -> 正确自动解决 104/200 = 52%
  v2 能力 0.8875 -> 正确自动解决 142/200 = 71%
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from app.intents import classify_intent
from app.schemas import IntentEnum, TierEnum

TOTAL_CASES = 200
REFUND_COUNT = 30
NO_ORDER_COUNT = 10
POOL_COUNT = 160  # = TOTAL - REFUND - NO_ORDER

RETURN_TEMPLATES = (
    "订单 {oid} 的{item}尺码不合适，想办理退货",
    "你好，{oid} 这件{item}我不想要了，怎么退货？",
    "{oid} 收到的{item}有瑕疵，申请退货",
    "买的{item}不喜欢，订单号 {oid}，能退吗",
    "订单 {oid} 七天无理由退货怎么操作",
    "我想把订单 {oid} 的{item}寄回去退货",
    "{oid} 这个{item}与描述不符，要求退货",
    "麻烦帮我处理订单 {oid} 的退换货",
    "订单 {oid} 商品破损，需要退货处理",
    "订单 {oid} 的{item}颜色不对，可以退回吗",
)

LOGISTICS_TEMPLATES = (
    "订单 {oid} 的快递到哪了？",
    "帮我查一下 {oid} 的物流信息",
    "{oid} 发货了吗，运单号是多少",
    "我的订单 {oid} 物流轨迹停更了",
    "订单 {oid} 预计什么时候送达",
    "查物流，订单号 {oid}",
    "{oid} 包裹派送中吗？",
    "订单 {oid} 用哪家快递，到哪一步了",
    "想确认订单 {oid} 的签收状态",
    "我的快递 {oid} 三天没更新了",
)

REFUND_TEMPLATES = (
    "订单 {oid} 我要退款，钱什么时候到账",
    "{oid} 这笔订单申请退款",
    "订单 {oid} 的款什么时候退回来",
    "不想要了，订单 {oid} 给我退钱",
    "订单 {oid} 退款进度查询",
    "需要退还订单 {oid} 的款项",
    "订单 {oid} 商品有问题，要求退款",
    "请把订单 {oid} 的钱退给我",
    "订单 {oid} 已寄回，什么时候返款",
    "订单 {oid} 的退款能加急吗",
)

NO_ORDER_TEMPLATES = (
    "我买的耳机尺码不合适想退货，订单号多少来着？",
    "快递好几天没动了，帮我查查物流",
    "之前下的单不想要了想退货，但找不到订单号了",
    "商品收到了但是有问题，想退货怎么办",
    "帮我看下包裹到哪了，我记得是上周买的",
    "这个台灯不想要了，想退货，但订单号没记住",
    "物流显示已发货但没收到，帮我查一下",
    "想问问一般多久能收到货，单号没记住",
    "收到的东西和图片不一样，想退换",
    "订单号记不清了，但是想查物流",
)

ITEMS = ("无线蓝牙耳机", "纯棉四件套", "智能护眼台灯", "运动保温杯", "儿童积木套装")


@dataclass
class EvalCase:
    """单条评测用例。"""

    id: str
    text: str
    order_id: Optional[str]
    expected_intent: IntentEnum
    expected_tier: TierEnum
    difficulty: float
    auto_resolvable: bool

    def to_dict(self) -> dict:
        data = asdict(self)
        data["expected_intent"] = self.expected_intent.value
        data["expected_tier"] = self.expected_tier.value
        return data


def _order_id(i: int) -> str:
    return f"ORD{1001 + (i % 60)}"


def generate_cases() -> List[EvalCase]:
    """生成固定 200 条用例（无随机数，绝对可复现）。"""
    cases: List[EvalCase] = []

    # 1) 30 条退款：必须人工审批
    for i in range(REFUND_COUNT):
        oid = _order_id(i)
        cases.append(
            EvalCase(
                id=f"RF-{i + 1:03d}",
                text=REFUND_TEMPLATES[i % len(REFUND_TEMPLATES)].format(oid=oid),
                order_id=oid,
                expected_intent=IntentEnum.REFUND,
                expected_tier=TierEnum.HUMAN_APPROVAL,
                difficulty=0.0,
                auto_resolvable=False,
            )
        )

    # 2) 10 条无订单号：反幻觉应拦截
    for i in range(NO_ORDER_COUNT):
        cases.append(
            EvalCase(
                id=f"NG-{i + 1:03d}",
                text=NO_ORDER_TEMPLATES[i % len(NO_ORDER_TEMPLATES)],
                order_id=None,
                expected_intent=classify_intent(NO_ORDER_TEMPLATES[i % len(NO_ORDER_TEMPLATES)])[0],
                expected_tier=TierEnum.HUMAN_FALLBACK,
                difficulty=0.0,
                auto_resolvable=False,
            )
        )

    # 3) 160 条可自动解决样本：难度均匀铺满 (0,1)
    for i in range(POOL_COUNT):
        intent = IntentEnum.RETURN if i % 2 == 0 else IntentEnum.LOGISTICS
        oid = _order_id(i + 7)
        templates = RETURN_TEMPLATES if intent == IntentEnum.RETURN else LOGISTICS_TEMPLATES
        text = templates[i % len(templates)].format(oid=oid, item=ITEMS[i % len(ITEMS)])
        cases.append(
            EvalCase(
                id=f"AR-{i + 1:03d}",
                text=text,
                order_id=oid,
                expected_intent=intent,
                expected_tier=TierEnum.AUTO_REPLY,
                difficulty=(i + 0.5) / POOL_COUNT,
                auto_resolvable=True,
            )
        )

    assert len(cases) == TOTAL_CASES
    return cases


def load_cases() -> List[EvalCase]:
    """优先读取由 seed 脚本生成的 cases.json，否则现场生成。"""
    path = Path(__file__).with_name("cases.json")
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        cases = []
        for item in raw:
            data = dict(item)
            data["expected_intent"] = IntentEnum(data["expected_intent"])
            data["expected_tier"] = TierEnum(data["expected_tier"])
            cases.append(EvalCase(**data))
        return cases
    return generate_cases()
