"""评测集与 A/B 框架测试。"""
from eval.ab import build_report
from eval.cases import generate_cases, load_cases
from eval.fixtures import HISTORICAL_RESULTS
from eval.run_eval import run_one
from app.schemas import IntentEnum, TierEnum


def test_case_set_size_and_composition():
    cases = generate_cases()
    assert len(cases) == 200
    assert len(load_cases()) == 200
    assert sum(c.expected_intent == IntentEnum.REFUND for c in cases) == 30
    assert sum(c.expected_tier == TierEnum.HUMAN_FALLBACK for c in cases) == 10
    assert sum(c.auto_resolvable for c in cases) == 160
    assert len({c.id for c in cases}) == 200


def test_live_eval_reproduces_resume_numbers():
    _, v1 = run_one("v1")
    _, v2 = run_one("v2")
    assert v1["auto_resolution_rate"] == 0.52
    assert v2["auto_resolution_rate"] == 0.71
    assert v1["net_resolution_rate"] == 0.24
    assert v2["net_resolution_rate"] == 0.62


def test_ab_cost_reduction():
    report = build_report(generate_cases())
    assert abs(report["delta"]["ai_cost_reduction"] - 0.30) < 1e-6
    assert report["delta"]["auto_resolution_rate_pp"] == 19.0


def test_historical_fixtures_match_live():
    _, v1 = run_one("v1")
    _, v2 = run_one("v2")
    for key in ("auto_resolution_rate", "net_resolution_rate", "ai_cost_per_ticket"):
        assert HISTORICAL_RESULTS["v1"][key] == v1[key]
        assert HISTORICAL_RESULTS["v2"][key] == v2[key]
