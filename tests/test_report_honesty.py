"""Evaluation-report truthfulness guard (dashboard truthfulness, fail-closed).

The deterministic promotion gate is NEGATIVE_NET_PNL and selection is always
blocked in this repo. A hand-maintained status ledger or a careless summary can
still OVERCLAIM: stamp `promoted: true`, a `verdict: PASS`, `robust_edge: true`
without the supporting evidence, or `profitable: true` while net PnL is negative.
Those claims would launder a blocked baseline into seeming "go-live ready".

This module is a fail-closed guard: `assert_truthful(report)` RAISES
`ReportHonestyError` (a `ValueError` subclass) when the report contains any
overclaim. It never edits the report, never promotes, never selects. It is
measurement/honesty only and stays compatible with `selection_blocked`.
"""
import pytest

from src.evaluation.report_honesty import (
    ReportHonestyError,
    assert_truthful,
    find_overclaims,
)


# --- forbidden promotion / selection keys -----------------------------------
def test_forbidden_promotion_key_raises():
    report = {"promoted": True}
    claims = find_overclaims(report)
    assert any("promoted" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


def test_multiple_forbidden_keys_all_reported():
    report = {"winner": True, "selected": True, "go_live_ready": True}
    claims = find_overclaims(report)
    assert len(claims) == 3
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


def test_false_promotion_key_is_not_an_overclaim():
    # The key exists but is falsy -> not an overclaim.
    claims = find_overclaims({"promoted": False})
    assert claims == []


# --- forbidden verdict strings ----------------------------------------------
def test_forbidden_verdict_string_raises():
    report = {"verdict": "PASS"}
    claims = find_overclaims(report)
    assert any("verdict" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


def test_lowercase_verdict_still_flagged():
    report = {"verdict": "positive"}
    assert any("verdict" in c for c in find_overclaims(report))


# --- robust_edge requires supporting evidence -------------------------------
def test_robust_edge_without_evidence_raises():
    report = {"robust_edge": True}
    claims = find_overclaims(report)
    assert any("robust_edge" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


def test_robust_edge_with_full_evidence_is_allowed():
    report = {
        "robust_edge": True,
        "dsr_positive": True,
        "adequate_sample": True,
        "holm_surviving": 1,
    }
    assert find_overclaims(report) == []
    assert_truthful(report)  # does not raise


def test_robust_edge_missing_holm_surviving_raises():
    report = {"robust_edge": True, "dsr_positive": True, "adequate_sample": True, "holm_surviving": 0}
    assert any("robust_edge" in c for c in find_overclaims(report))


# --- profitability claim contradicting non-positive PnL ---------------------
def test_profitable_claim_with_negative_pnl_raises():
    report = {"profitable": True, "net_pnl": -100.0}
    claims = find_overclaims(report)
    assert any("profitable" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


def test_profitable_claim_with_positive_pnl_allowed():
    report = {"profitable": True, "net_pnl": 100.0}
    assert find_overclaims(report) == []
    assert_truthful(report)


def test_profitable_claim_with_non_numeric_pnl_raises():
    report = {"profitable": True, "net_pnl": "n/a"}
    assert any("profitable" in c for c in find_overclaims(report))


# --- explicit promotion_gate contradiction ----------------------------------
def test_promotion_gate_positive_while_blocked_raises():
    report = {"promotion_gate": "POSITIVE", "selection_blocked": True}
    claims = find_overclaims(report)
    assert any("promotion_gate" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


# --- honest reports pass -----------------------------------------------------
def test_empty_report_is_safe():
    assert find_overclaims({}) == []
    assert_truthful({})


def test_fully_honest_blocked_report_passes():
    report = {
        "selection_blocked": True,
        "deterministic_baseline_gate": "NEGATIVE_NET_PNL",
        "net_pnl": -6872.31,
        "adequate_sample": True,
        "robust_edge": False,
    }
    assert find_overclaims(report) == []
    assert_truthful(report)


def test_non_dict_raises_typeerror():
    with pytest.raises(TypeError):
        find_overclaims([])  # type: ignore[arg-type]


# --- integration: real baseline payload is truthful, tampered raises --------
def _assemble_baseline_payload():
    from scripts.run_strategy_baseline import make_series
    from src.evaluation.baseline import run_baseline, run_walk_forward, run_cost_stress
    from src.evaluation.stress import run_stress_matrix
    from src.evaluation.statistics import compute_statistics

    series = make_series()
    result = run_baseline(series)
    payload = dict(result.__dict__)
    payload["walk_forward_evaluation"] = run_walk_forward(series)
    payload["cost_stress"] = run_cost_stress(series)
    payload["stress_matrix"] = run_stress_matrix(series)
    payload["statistics"] = compute_statistics(result.trade_pnls)
    payload["selection_blocked"] = True
    payload["report_honest"] = True
    return payload


def test_real_baseline_payload_is_truthful():
    payload = _assemble_baseline_payload()
    assert payload["selection_blocked"] is True
    # The genuine, un-tampered baseline report must pass the guard.
    assert find_overclaims(payload) == []
    assert_truthful(payload)


def test_tampered_baseline_payload_is_rejected():
    payload = _assemble_baseline_payload()
    # A careless summary that claims a winner while selection is blocked.
    payload["winner"] = True
    claims = find_overclaims(payload)
    assert any("winner" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(payload)
