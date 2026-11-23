"""Seed 脚本：生成 eval/cases.json（200 条评测用例）。

运行：
    python eval/seed_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.cases import generate_cases  # noqa: E402


def main() -> None:
    cases = generate_cases()
    target = Path(__file__).with_name("cases.json")
    target.write_text(
        json.dumps([c.to_dict() for c in cases], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已生成 {len(cases)} 条评测用例 -> {target.name}")


if __name__ == "__main__":
    main()
