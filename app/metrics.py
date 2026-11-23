"""指标定义、成本估算与 A/B 成本对比。

============================ 指标口径（重要）============================

【自动解决率 auto_resolution_rate】
    auto_resolution_rate = 正确自动解决的工单数 / 总工单数
    即简历中「自动解决率由 52% 升至 71%」所指的指标。

【净解决率 net_resolution_rate】——本项目定义的核心指标
    设想：错误地转人工（本可自动解决却转人工）是一种隐性失败，
    它既增加人工成本，又把本来能自动闭环的咨询推回人工，应从成绩中扣减。

        net_resolved = auto_resolved - false_escalations
        net_resolution_rate = net_resolved / total

    其中：
      - auto_resolved      : 由 Agent 正确自动回复并闭环的工单数
      - false_escalations  : 错误升级工单数（本可自动解决，却因模型能力不足
                             被转人工）；退款这类「本就应转人工」的不计入
      - total              : 评测集工单总数

    该指标比自动解决率更保守，用于衡量「真实可用的自动化收益」。

【错误升级率 false_escalation_rate】
    false_escalation_rate = false_escalations / total

【单笔服务成本 cost_per_ticket】
    单笔成本 = LLM 输入 token 成本 + LLM 输出 token 成本 + 人工处理成本
    LLM 输入成本 = token_in / 1000 * PRICE_INPUT_PER_1K
    LLM 输出成本 = token_out / 1000 * PRICE_OUTPUT_PER_1K
    人工处理成本 = HUMAN_COST_PER_TICKET（仅转人工工单计入）

    因此成本下降来自两条路径：
      1) 更简洁的提示词 -> token 下降；
      2) 更高的自动解决率 -> 转人工数量下降（主因）。
"""
from __future__ import annotations

import os
from typing import Dict, List

# 单价可通过 .env / 环境变量覆盖
PRICE_INPUT_PER_1K = float(os.getenv("PRICE_INPUT_PER_1K", "0.0015"))
PRICE_OUTPUT_PER_1K = float(os.getenv("PRICE_OUTPUT_PER_1K", "0.0020"))
HUMAN_COST_PER_TICKET = float(os.getenv("HUMAN_COST_PER_TICKET", "8.0"))

FORMULA_DOC = (
    "net_resolved = auto_resolved - false_escalations; "
    "net_resolution_rate = net_resolved / total"
)


def estimate_cost(
    token_in: int,
    token_out: int,
    escalated: bool,
    *,
    price_in: float = PRICE_INPUT_PER_1K,
    price_out: float = PRICE_OUTPUT_PER_1K,
    human_cost: float = HUMAN_COST_PER_TICKET,
) -> float:
    """估算单个工单的服务成本（元）。"""
    llm_cost = (token_in / 1000.0) * price_in + (token_out / 1000.0) * price_out
    return llm_cost + (human_cost if escalated else 0.0)


def compute_metrics(records: List[Dict]) -> Dict[str, float | int]:
    """从评测记录计算全部指标。

    records 每条至少包含:
        auto_resolved(bool), escalated(bool), false_escalation(bool),
        token_in(int), token_out(int)
    """
    total = len(records)
    if total == 0:
        raise ValueError("评测记录为空")

    auto_resolved = sum(1 for r in records if r.get("auto_resolved"))
    escalated = sum(1 for r in records if r.get("escalated"))
    false_escalations = sum(1 for r in records if r.get("false_escalation"))

    net_resolved = auto_resolved - false_escalations
    total_token_in = sum(int(r.get("token_in", 0)) for r in records)
    total_token_out = sum(int(r.get("token_out", 0)) for r in records)

    llm_cost = sum(
        int(r.get("token_in", 0)) / 1000.0 * PRICE_INPUT_PER_1K
        + int(r.get("token_out", 0)) / 1000.0 * PRICE_OUTPUT_PER_1K
        for r in records
    )
    human_cost = escalated * HUMAN_COST_PER_TICKET
    total_cost = llm_cost + human_cost

    return {
        "total": total,
        "auto_resolved": auto_resolved,
        "escalated": escalated,
        "false_escalations": false_escalations,
        "net_resolved": net_resolved,
        "auto_resolution_rate": round(auto_resolved / total, 4),
        "net_resolution_rate": round(net_resolved / total, 4),
        "false_escalation_rate": round(false_escalations / total, 4),
        "escalation_rate": round(escalated / total, 4),
        "total_token_in": total_token_in,
        "total_token_out": total_token_out,
        "llm_cost": round(llm_cost, 4),
        "human_cost": round(human_cost, 4),
        "total_cost": round(total_cost, 4),
        # AI 服务单笔成本（不含人工），简历中「-30%」即此口径
        "ai_cost_per_ticket": round(llm_cost / total, 6),
        # 综合单笔成本（含人工）
        "cost_per_ticket": round(total_cost / total, 4),
    }


def cost_reduction(baseline: Dict, candidate: Dict) -> float:
    """返回候选版本相对基线的单笔成本下降比例（0.30 表示下降 30%）。"""
    base = baseline["cost_per_ticket"]
    if not base:
        raise ValueError("基线成本为 0，无法计算下降比例")
    return (base - candidate["cost_per_ticket"]) / base
