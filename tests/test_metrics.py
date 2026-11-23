"""指标公式与成本估算测试。"""
import pytest

from app.metrics import (
    compute_metrics,
    cost_reduction,
    estimate_cost,
)


def _record(auto: bool, escalated: bool, false_esc: bool) -> dict:
    return {
        "auto_resolved": auto,
        "escalated": escalated,
        "false_escalation": false_esc,
        "token_in": 440,
        "token_out": 90,
    }


def test_net_resolution_formula():
    records = [_record(True, False, False) for _ in range(6)]
    records += [_record(False, True, True) for _ in range(2)]   # 错误升级
    records += [_record(False, True, False) for _ in range(2)]  # 本就应转人工
    metrics = compute_metrics(records)

    assert metrics["auto_resolved"] == 6
    assert metrics["false_escalations"] == 2
    assert metrics["net_resolved"] == 4  # 6 - 2
    assert metrics["auto_resolution_rate"] == 0.6
    assert metrics["net_resolution_rate"] == 0.4
    assert metrics["false_escalation_rate"] == 0.2


def test_estimate_cost():
    # 440 in * 0.0015/1000 + 90 out * 0.002/1000
    solo = estimate_cost(440, 90, False)
    assert abs(solo - (440 / 1000 * 0.0015 + 90 / 1000 * 0.002)) < 1e-9
    escalated = estimate_cost(440, 90, True)
    assert abs(escalated - solo - 8.0) < 1e-9


def test_cost_reduction():
    base = {"cost_per_ticket": 1.0}
    candidate = {"cost_per_ticket": 0.7}
    assert abs(cost_reduction(base, candidate) - 0.3) < 1e-9
    with pytest.raises(ValueError):
        cost_reduction({"cost_per_ticket": 0}, candidate)


def test_empty_records():
    with pytest.raises(ValueError):
        compute_metrics([])
