"""Strengthen walk-forward evaluation (focus #2 of the autonomous mandate).

Two honest-edge gaps this module closes:

1. The walk-forward pipeline reports aggregate net PnL and a window-level bootstrap
   CI, but it never asks: "how many INDIVIDUAL walk-forward windows survive a
   multiple-testing correction?" A strategy that aggregates to a positive point
   estimate because ONE of 50 windows happened to be lucky is not robust edge.
   We add a per-window one-sided bootstrap test and a Holm step-down correction
   across windows.

2. A high Sharpe ratio is easy to fake with a single lucky run because of
   multiple-testing and non-Normal trade distributions. We add a Deflated Sharpe
   Ratio (Bailey & Lopez de Prado) that discounts the observed Sharpe by the
   number of trials and the trade distribution's skew/kurtosis.

This is MEASUREMENT ONLY. Every function here keeps ``selection_blocked`` True and
never emits ``promoted`` / ``selected`` / ``winner`` keys, so it stays compatible
with the always-blocked Phase 6 deterministic promotion gate.
"""
import pytest

from src.evaluation.baseline import BaselineConfig, run_walk_forward
from scripts.run_strategy_baseline import make_series
from src.evaluation.walk_forward_strength import (
    window_one_sided_p,
    holm_stepdown,
    deflated_sharpe,
    strengthen_walk_forward,
)


# --- Precondition: walk-forward must expose per-window trade PnLs (RED before impl) ---
def test_walk_forward_attaches_per_window_trade_pnls():
    """Per-window multiple-testing needs the actual trades inside each window.

    If ``run_walk_forward`` does not carry ``trade_pnls`` per window, the
    strengthen step cannot bootstrap individual windows and the honest-edge
    guard silently degrades to the old window-level aggregate.
    """
    series = make_series(48)
    wf = run_walk_forward(series, BaselineConfig())
    assert wf, "expected at least one walk-forward window"
    for row in wf:
        assert "trade_pnls" in row
        assert isinstance(row["trade_pnls"], list)


# --- window_one_sided_p -----------------------------------------------------------
def test_window_p_rejects_clearly_positive_window():
    # All positive trades -> the one-sided null (mean <= 0) is decisively rejected.
    p = window_one_sided_p([10.0, 20.0, 15.0, 5.0, 12.0], seed=0)
    assert 0.0 <= p <= 1.0
    assert p < 0.05


def test_window_p_keeps_null_for_negative_window():
    p = window_one_sided_p([-10.0, -20.0, -15.0], seed=0)
    assert 0.5 < p <= 1.0


def test_window_p_is_bounded_and_deterministic():
    trades = [1.0, -5.0, 3.0, 2.0, -8.0, 4.0, -1.0, 6.0]
    p1 = window_one_sided_p(trades, seed=7)
    p2 = window_one_sided_p(trades, seed=7)
    assert p1 == p2  # deterministic given seed
    assert 0.0 <= p1 <= 1.0


def test_window_p_rejects_on_empty_fail_closed():
    with pytest.raises(ValueError, match="window"):
        window_one_sided_p([], seed=0)


# --- holm_stepdown ---------------------------------------------------------------
def test_holm_rejects_only_the_strongly_significant_window():
    ps = [0.001, 0.4, 0.9]
    rejected, count = holm_stepdown(ps, alpha=0.05)
    assert rejected[0] is True
    assert rejected[1] is False and rejected[2] is False
    assert count == 1


def test_holm_rejects_none_when_all_large():
    ps = [0.5, 0.6, 0.7]
    rejected, count = holm_stepdown(ps, alpha=0.05)
    assert count == 0
    assert not any(rejected)


def test_holm_respects_alpha_in_threshold():
    # At alpha=0.10 the 2nd smallest (0.06) is below 0.10/2 = 0.05? No -> only first.
    ps = [0.02, 0.06, 0.8]
    rejected, count = holm_stepdown(ps, alpha=0.10)
    assert rejected[0] is True
    # 0.06 > 0.10/2 = 0.05 -> step-down stops.
    assert rejected[1] is False
    assert count == 1


# --- deflated_sharpe -------------------------------------------------------------
def test_dsr_low_for_zero_mean_high_variance_no_edge():
    import random
    rng = random.Random(1)
    trades = [rng.gauss(0.0, 1.0) for _ in range(50)]
    out = deflated_sharpe(trades, trials=10, seed=0)
    assert 0.0 <= out["dsr_prob"] <= 1.0
    # Mean ~0 but trials inflate the false-discovery Sharpe, so DSR must be low.
    assert out["dsr_prob"] < 0.5
    assert out["dsr_positive"] is False
    assert "sharpe" in out and "expected_false_sharpe" in out


def test_dsr_high_for_degenerate_consistent_positive():
    # Zero-variance positive trades: there is no uncertainty, so DSR = 1.0.
    out = deflated_sharpe([2.0] * 40, trials=10, seed=0)
    assert out["dsr_prob"] == 1.0
    assert out["dsr_positive"] is True


def test_dsr_fails_closed_on_too_few_observations():
    out = deflated_sharpe([1.0], trials=1, seed=0)
    assert out["dsr_prob"] == 0.0
    assert out["dsr_positive"] is False


def test_dsr_expected_false_sharpe_grows_with_trials():
    t1 = deflated_sharpe([0.5] * 60, trials=1, seed=0)["expected_false_sharpe"]
    t10 = deflated_sharpe([0.5] * 60, trials=10, seed=0)["expected_false_sharpe"]
    # More trials tested -> higher bar (expected maximum Sharpe among trials).
    assert t10 > t1 >= 0.0


# --- strengthen_walk_forward (orchestration, measurement only) -------------------
def test_strengthen_never_promotes_and_reports_components():
    rows = [
        {"net_pnl": 100.0, "closed_trades": 40, "trade_pnls": [10.0, 5.0, 8.0, -2.0, 12.0] * 8},
        {"net_pnl": -50.0, "closed_trades": 40, "trade_pnls": [1.0, -5.0, 3.0, 2.0, -8.0] * 8},
    ]
    out = strengthen_walk_forward(rows, min_closed_trades=30, confidence=0.95, seed=0)
    assert out["selection_blocked"] is True
    assert "promoted" not in out and "selected" not in out and "winner" not in out
    assert out["windows"] == 2
    assert isinstance(out["holm_surviving"], int) and out["holm_surviving"] >= 0
    assert 0.0 <= out["dsr_prob"] <= 1.0
    assert out["adequate_sample"] is True  # 80 trades >= 30
    # Measurement-only facts we deliberately expose for the report:
    for key in ("holm_surviving", "holm_total", "dsr_prob", "dsr_positive",
                "expected_false_sharpe", "adequate_sample", "robust_edge"):
        assert key in out


def test_strengthen_fails_closed_without_adequate_sample():
    rows = [
        {"net_pnl": 100.0, "closed_trades": 5, "trade_pnls": [10.0, 5.0, 8.0, -2.0, 12.0]},
        {"net_pnl": 50.0, "closed_trades": 5, "trade_pnls": [1.0, 5.0, 3.0, 2.0, 8.0]},
    ]
    out = strengthen_walk_forward(rows, min_closed_trades=30, confidence=0.95, seed=0)
    assert out["adequate_sample"] is False
    # Fail closed: an inadequate sample can never be "robust edge".
    assert out["robust_edge"] is False
    assert out["selection_blocked"] is True


def test_strengthen_consumes_real_walk_forward_rows():
    series = make_series(50)
    wf = run_walk_forward(series, BaselineConfig())
    out = strengthen_walk_forward(wf, min_closed_trades=30, confidence=0.95, seed=0)
    assert out["selection_blocked"] is True
    assert out["windows"] == len(wf)
    assert out["holm_total"] == sum(1 for r in wf if r.get("trade_pnls"))


def test_strengthen_rejects_empty_rows_fail_closed():
    with pytest.raises(ValueError, match="strengthen"):
        strengthen_walk_forward([], min_closed_trades=30, confidence=0.95, seed=0)
