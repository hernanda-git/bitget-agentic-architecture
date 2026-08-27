"""Recursion hardening for the report-truthfulness guard (dashboard truthfulness).

Phase 17 wired ``assert_truthful`` into the real-history entrypoint but its own
Limitations section named a gap: the guard only inspected the TOP LEVEL of the
report dict, so a forbidden ``promoted``/``winner``/``selection`` key nested
inside an unrelated sub-dict would NOT be flagged. This module closes that gap
by recursing into nested dicts and lists.

Design note (pre-validated empirically): the recursion set deliberately EXCLUDES
``selected``. Legitimate evaluation dicts can carry sub-keys such as
``selected_feature`` / ``selected_strategy``; a nested ``selected`` is not, by
itself, proof of a selection overclaim. The top-level ``selected`` check is
unchanged. All other overclaim signals (winner, promoted, go_live_ready,
verdict strings, profitable, promotion_gate) are recursed because they are
unambiguous overclaims wherever they appear. A depth cap prevents pathological
structures from looping forever.
"""
import pytest

from src.evaluation.report_honesty import (
    MAX_SCAN_DEPTH,
    ReportHonestyError,
    assert_truthful,
    find_overclaims,
)


# --- nested forbidden promotion / selection keys ---------------------------
def test_nested_forbidden_promotion_key_flagged():
    report = {"selection_blocked": True, "candidates": {"winner": True}}
    claims = find_overclaims(report)
    assert any("winner" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


def test_nested_forbidden_promotion_key_in_list_of_dicts_flagged():
    report = {"selection_blocked": True, "rows": [{"promoted": True}]}
    claims = find_overclaims(report)
    assert any("promoted" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


def test_nested_two_levels_deep_flagged():
    report = {"selection_blocked": True, "a": {"b": {"go_live_ready": True}}}
    claims = find_overclaims(report)
    assert any("go_live_ready" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


# --- nested forbidden verdict strings ---------------------------------------
def test_nested_forbidden_verdict_flagged():
    report = {"selection_blocked": True, "summary": {"verdict": "PASS"}}
    claims = find_overclaims(report)
    assert any("verdict" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


def test_nested_neutral_verdict_not_flagged():
    # "NEUTRAL" is a legitimate per-window verdict, not an overclaim.
    claims = find_overclaims({"summary": {"verdict": "NEUTRAL"}})
    assert claims == []


# --- nested profitability contradiction -------------------------------------
def test_nested_profitable_contradiction_flagged():
    report = {
        "selection_blocked": True,
        "detail": {"profitable": True, "net_pnl": -5.0},
    }
    claims = find_overclaims(report)
    assert any("profitable" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


# --- nested promotion_gate contradiction -------------------------------------
def test_nested_promotion_gate_while_blocked_flagged():
    report = {
        "selection_blocked": True,
        "summary": {"promotion_gate": "POSITIVE"},
    }
    claims = find_overclaims(report)
    assert any("promotion_gate" in c for c in claims)
    with pytest.raises(ReportHonestyError):
        assert_truthful(report)


# --- recursion must not false-positive on legitimate nested keys ------------
def test_legitimate_nested_fields_not_flagged():
    report = {
        "selection_blocked": True,
        "walk_forward_evaluation": {
            "verdict": "NEUTRAL",
            "selected_feature": "momentum",
            "holm_surviving": 0,
        },
        "statistics": {"mean": 1.0, "selected": "baseline"},
    }
    # A nested `selected` (e.g. selected feature/strategy) must NOT be treated
    # as a selection overclaim; only the top-level `selected` check applies.
    assert find_overclaims(report) == []
    assert_truthful(report)


# --- depth cap prevents infinite recursion on pathological structures --------
def _deep_chain(depth: int, key=None, value=None):
    node: dict = {}
    cur = node
    for _ in range(depth):
        nxt: dict = {}
        cur["a"] = nxt
        cur = nxt
    if key is not None:
        cur[key] = value
    return node


def test_deep_chain_without_forbidden_key_terminates():
    # A 100-level structure with no forbidden key must return promptly (no hang)
    # and report no overclaims.
    report = _deep_chain(100)
    claims = find_overclaims(report)
    assert claims == []


def test_deep_chain_within_depth_is_flagged():
    # A forbidden key well within MAX_SCAN_DEPTH must still be caught.
    report = _deep_chain(MAX_SCAN_DEPTH - 5, key="winner", value=True)
    claims = find_overclaims(report)
    assert any("winner" in c for c in claims)


def test_excessive_depth_key_is_not_flagged_but_terminates():
    # A forbidden key buried deeper than MAX_SCAN_DEPTH evades the scan (a
    # bounded, documented limitation) but the call must still terminate.
    report = _deep_chain(MAX_SCAN_DEPTH + 50, key="winner", value=True)
    claims = find_overclaims(report)
    # No hang, and the beyond-depth key is intentionally not scanned.
    assert isinstance(claims, list)
