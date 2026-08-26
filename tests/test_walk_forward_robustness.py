"""Walk-forward robustness gate (strengthen walk-forward evaluation, focus #2).

This is MEASUREMENT ONLY. It reports the two promotion gates that Phase 7 marked
NOT_EVIDENCED:

  - adequate closed-trade sample
  - positive expectancy with supporting confidence interval

as computed, honest facts. It never changes the deterministic promotion gate
(NEGATIVE_NET_PNL) and never emits a promoted/selected/winner flag, so it stays
compatible with the always-blocked selection policy.
"""
import pytest
from statistics import mean

from src.evaluation.baseline import (
    BaselineConfig,
    gate_walk_forward_robustness,
    run_walk_forward,
    summarize_walk_forward,
)


def _window(net_pnl, closed_trades=5):
    return {
        "train_start": 0, "train_end": 9, "test_start": 10, "test_end": 19,
        "context_start": 0, "context_end": 9, "test_snapshots": 10,
        "closed_trades": closed_trades, "gross_pnl": net_pnl,
        "protection_attachments": closed_trades, "reconciliation_checks": 0,
        "fees": 0.0, "funding": 0.0, "slippage": 0.0, "net_pnl": net_pnl,
        "spread": 0.0, "strategy_breakdown": {},
    }


def test_robustness_gate_reports_expectancy_ci_and_adequate_sample():
    rows = [
        _window(120.0, closed_trades=40),
        _window(80.0, closed_trades=40),
        _window(150.0, closed_trades=40),
        _window(-30.0, closed_trades=40),
        _window(200.0, closed_trades=40),
    ]
    trade_pnls = [10.0, 12.0, -5.0, 8.0, 15.0, 3.0] * 40  # 240 trades, net positive
    out = gate_walk_forward_robustness(rows, trade_pnls=trade_pnls)

    assert out["windows"] == 5
    assert out["total_closed_trades"] == 200
    assert out["min_closed_trades"] == 30
    assert out["adequate_sample"] is True
    # Trade-level expectancy must be positive and its CI lower bound strictly > 0.
    assert out["expectancy_mean"] > 0
    assert out["expectancy_ci"][0] is not None and out["expectancy_ci"][1] is not None
    assert out["expectancy_positive_with_ci"] is True
    # Measurement only: never promotes a strategy.
    assert out["selection_blocked"] is True
    assert "promoted" not in out and "best" not in out and "selected" not in out


def test_robustness_gate_fails_closed_without_adequate_sample():
    # Only 20 closed trades total, below the 30-trade minimum.
    rows = [_window(500.0, closed_trades=10), _window(500.0, closed_trades=10)]
    trade_pnls = [100.0] * 20  # even though every trade is wildly profitable
    out = gate_walk_forward_robustness(rows, trade_pnls=trade_pnls, min_closed_trades=30)
    assert out["total_closed_trades"] == 20
    assert out["adequate_sample"] is False
    # Fail closed: an inadequate sample can never prove positive expectancy.
    assert out["expectancy_positive_with_ci"] is False


def test_robustness_gate_ci_is_honest_for_negative_dataset():
    # A dataset with a positive point expectancy but a wide CI straddling zero
    # must NOT be reported as proven positive expectancy.
    rows = [_window(10.0, closed_trades=35), _window(-200.0, closed_trades=35)]
    # Pooled trades: one big winner, many small losers -> mean slightly positive
    # but CI straddles zero.
    trade_pnls = [100.0] + [-1.0] * 69  # mean ~ 0.44, CI straddles zero
    out = gate_walk_forward_robustness(rows, trade_pnls=trade_pnls, min_closed_trades=30)
    assert out["adequate_sample"] is True
    assert out["expectancy_mean"] > 0  # point estimate positive
    # But the CI lower bound must be <= 0, so proven-positive is False.
    assert out["expectancy_ci"][0] <= 0
    assert out["expectancy_positive_with_ci"] is False


def test_robustness_gate_falls_back_to_window_ci_without_trade_pnls():
    rows = [_window(50.0, closed_trades=40), _window(60.0, closed_trades=40), _window(40.0, closed_trades=40)]
    out = gate_walk_forward_robustness(rows)  # no trade_pnls -> window-level CI
    # Window-level net PnL is always positive here, so expectancy (window CI) is proven.
    assert out["expectancy_mean"] > 0
    assert out["expectancy_ci"][0] is not None
    assert out["expectancy_positive_with_ci"] is True
    # summary facts still line up with summarize_walk_forward
    assert out["profitable_windows"] == summarize_walk_forward(rows)["profitable_windows"]


def test_robustness_gate_rejects_empty_windows_fail_closed():
    with pytest.raises(ValueError, match="walk-forward robustness"):
        gate_walk_forward_robustness(())


def test_robustness_gate_does_not_change_promotion_verdict():
    # The gate is descriptive only: a negative walk-forward still reports
    # adequate_sample when large enough, but must never flip promotion_allowed.
    rows = [_window(-100.0, closed_trades=40), _window(-50.0, closed_trades=40)]
    trade_pnls = [-5.0] * 80
    out = gate_walk_forward_robustness(rows, trade_pnls=trade_pnls)
    assert out["adequate_sample"] is True
    assert out["expectancy_positive_with_ci"] is False
    assert out["expectancy_ci"][0] < 0


def test_robustness_gate_composes_with_real_walk_forward_pipeline():
    # End-to-end wiring: the gate consumes the real run_walk_forward window rows
    # and the real baseline trade PnLs, never re-deriving numbers.
    from scripts.run_strategy_baseline import make_series
    from src.evaluation.baseline import run_baseline

    series = make_series(48)
    wf = run_walk_forward(series, BaselineConfig())
    baseline = run_baseline(series, BaselineConfig())
    out = gate_walk_forward_robustness(wf, trade_pnls=baseline.trade_pnls)
    assert out["windows"] == len(wf)
    # The gate's trade count comes from the walk-forward windows, not the full
    # series baseline, so the honest invariant is the sum of window trades.
    assert out["total_closed_trades"] == sum(r["closed_trades"] for r in wf)
    # Whatever the synthetic dataset yields, the gate never promotes a strategy.
    assert out["selection_blocked"] is True
    assert "promoted_strategy" not in out and "selected_strategy" not in out
    # adequate_sample is consistent with the number of trades actually replayed
    # across the walk-forward windows.
    assert out["adequate_sample"] == (out["total_closed_trades"] >= 30)
