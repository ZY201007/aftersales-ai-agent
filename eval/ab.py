"""A/B 对比工具：比较两个 Agent 版本的解决率与单笔成本。

运行：
    python eval/ab.py                 # 实时跑 200 条用例对比 v1 vs v2
    python eval/ab.py --mode fixtures # 打印简历中的历史实测结果
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.cases import load_cases  # noqa: E402
from eval.fixtures import HISTORICAL_RESULTS  # noqa: E402
from eval.run_eval import run_one  # noqa: E402


def build_report(cases) -> dict:
    _, m1 = run_one("v1", cases)
    _, m2 = run_one("v2", cases)
    return {
        "cases": len(cases),
        "v1": m1,
        "v2": m2,
        "delta": {
            "auto_resolution_rate_pp": round(
                (m2["auto_resolution_rate"] - m1["auto_resolution_rate"]) * 100, 1
            ),
            "net_resolution_rate_pp": round(
                (m2["net_resolution_rate"] - m1["net_resolution_rate"]) * 100, 1
            ),
            "ai_cost_reduction": round(
                (m1["ai_cost_per_ticket"] - m2["ai_cost_per_ticket"])
                / m1["ai_cost_per_ticket"],
                4,
            ),
            "total_cost_reduction": round(
                (m1["cost_per_ticket"] - m2["cost_per_ticket"]) / m1["cost_per_ticket"],
                4,
            ),
        },
    }


def print_report(report: dict, title: str, historical: bool = False) -> None:
    print(f"\n===== {title} =====")
    print(f"用例数: {report['cases'] if not historical else 200}")
    for version in ("v1", "v2"):
        item = report[version]
        print(
            f"  {version}: 自动解决率={item['auto_resolution_rate']:.1%} | "
            f"净解决率={item['net_resolution_rate']:.1%} | "
            f"AI单笔=¥{item['ai_cost_per_ticket']:.6f} | "
            f"综合单笔=¥{item['cost_per_ticket']:.2f}"
        )
    d = report["delta"]
    print(
        f"  差异: 自动解决率 +{d['auto_resolution_rate_pp']}pp | "
        f"净解决率 +{d['net_resolution_rate_pp']}pp | "
        f"AI 单笔成本 -{d['ai_cost_reduction']:.1%} | "
        f"综合单笔成本 -{d['total_cost_reduction']:.1%}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="售后星 A/B 对比")
    parser.add_argument("--mode", choices=["live", "fixtures"], default="live")
    parser.add_argument("--output", default=None)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    if args.mode == "fixtures":
        print_report(HISTORICAL_RESULTS, "历史实测结果（简历数字）", historical=True)
        print(f"\n注: {HISTORICAL_RESULTS['note']}")
        return

    report = build_report(load_cases())
    print_report(report, "实时评测 A/B 对比（MockLLM）")
    if not args.no_save:
        target = Path(args.output) if args.output else (
            Path(__file__).with_name("results") / "ab_report.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已保存: {target}")


if __name__ == "__main__":
    main()
