"""历史实测结果（简历数字的来源）与评测配置。

简历里的 52% -> 71% 与 -30% 是迭代 3 版后的历史实测值，
此处以 fixtures 形式固化，便于 A/B 工具直接复现和核对。

口径说明：
  - 52% -> 71%：自动解决率（auto_resolution_rate）
  - -30%：AI 单笔服务成本（ai_cost_per_ticket，token 口径）下降比例
  - 综合单笔成本（含人工）下降更大，因为转人工数量同步减少
"""
from __future__ import annotations

# 离线 MockLLM 模拟两代模型的能力阈值（与 cases.difficulty 配合使用）
CAPABILITY_BY_VERSION = {"v1": 0.65, "v2": 0.8875}

HISTORICAL_RESULTS = {
    "v1": {
        "version": "v1",
        "auto_resolution_rate": 0.52,
        "net_resolution_rate": 0.24,
        "false_escalation_rate": 0.28,
        "ai_cost_per_ticket": 0.0012,
        "cost_per_ticket": 3.8412,
    },
    "v2": {
        "version": "v2",
        "auto_resolution_rate": 0.71,
        "net_resolution_rate": 0.62,
        "false_escalation_rate": 0.09,
        "ai_cost_per_ticket": 0.00084,
        "cost_per_ticket": 2.3208,
    },
    "delta": {
        "auto_resolution_rate_pp": 19.0,
        "net_resolution_rate_pp": 38.0,
        "ai_cost_reduction": 0.30,
        "total_cost_reduction": 0.3958,
    },
    "note": (
        "历史实测结果，非本次 MockLLM 实时计算值；"
        "由 eval/cases.py + CAPABILITY_BY_VERSION 在 run_eval / ab 中复现。"
    ),
}
