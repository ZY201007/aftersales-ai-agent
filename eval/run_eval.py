"""离线评测入口：对 200 条用例跑 Agent 并计算指标。

运行：
    python eval/run_eval.py --version v2
    python -m eval.run_eval --version v1
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import AfterSalesAgent, VERSION_PRESETS  # noqa: E402
from app.approval import ApprovalQueue  # noqa: E402
from app.llm import MockLLM  # noqa: E402
from app.metrics import compute_metrics  # noqa: E402
from app.schemas import CustomerMessage  # noqa: E402
from app.tools import ToolRegistry  # noqa: E402
from eval.cases import EvalCase, load_cases  # noqa: E402
from eval.fixtures import CAPABILITY_BY_VERSION  # noqa: E402


def run_one(version: str, cases: List[EvalCase] | None = None) -> Tuple[list, dict]:
    """跑单个版本，返回 (逐条记录, 汇总指标)。"""
    cases = cases or load_cases()
    config = replace(
        VERSION_PRESETS[version],
        simulated_capability=CAPABILITY_BY_VERSION[version],
    )
    agent = AfterSalesAgent(MockLLM(), ToolRegistry(), ApprovalQueue(), config)

    records = []
    for case in cases:
        response = agent.handle(
            CustomerMessage(
                text=case.text, order_id=case.order_id, session_id=case.id
            ),
            difficulty=case.difficulty,
        )
        records.append(
            {
                "case_id": case.id,
                "expected_intent": case.expected_intent.value,
                "actual_intent": response.intent.value,
                "expected_tier": case.expected_tier.value,
                "actual_tier": response.tier.value,
                "auto_resolved": response.auto_resolved,
                "escalated": response.escalated,
                "false_escalation": response.false_escalation,
                "token_in": response.token_in,
                "token_out": response.token_out,
            }
        )
    return records, compute_metrics(records)


def format_metrics(version: str, metrics: dict) -> str:
    return (
        f"[{version}] 用例数={metrics['total']} | "
        f"自动解决率={metrics['auto_resolution_rate']:.1%} | "
        f"净解决率={metrics['net_resolution_rate']:.1%} | "
        f"错误升级={metrics['false_escalations']} | "
        f"AI单笔成本=¥{metrics['ai_cost_per_ticket']:.6f} | "
        f"综合单笔成本=¥{metrics['cost_per_ticket']:.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="售后星离线评测")
    parser.add_argument("--version", choices=["v1", "v2"], default="v2")
    parser.add_argument("--output", default=None, help="结果 JSON 路径")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    records, metrics = run_one(args.version)
    print(format_metrics(args.version, metrics))
    intent_ok = sum(r["expected_intent"] == r["actual_intent"] for r in records)
    print(f"意图分类准确率: {intent_ok / len(records):.1%} ({intent_ok}/{len(records)})")

    if not args.no_save:
        target = Path(args.output) if args.output else (
            Path(__file__).with_name("results") / f"eval_{args.version}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"metrics": metrics, "records": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"结果已保存: {target}")


if __name__ == "__main__":
    main()
