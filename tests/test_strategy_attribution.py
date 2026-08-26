"""Independent per-strategy walk-forward attribution (strategy attribution, focus #3).

Each strategy is replayed ALONE across the same walk-forward windows so its
signal can be attributed without the other strategies' trades masking or
inflating it. This is measurement only:

- No strategy is selected, ranked, or promoted to a "winner" role.
- The test set is never used to pick a strategy (no walk-forward peeking).
- `selection_blocked` is always true so downstream code cannot treat one
  strategy as the promoted candidate.

The deterministic promotion gate (NEGATIVE_NET_PNL) remains the only thing
that may unblock Phase 6, and this module never influences it.
"""
import pytest
from dataclasses import replace

from src.evaluation.baseline import (
    BaselineConfig,
    run_strategy_attribution,
    run_walk_forward,
    summarize_walk_forward,
)
from scripts.run_strategy_baseline import make_series
from src.strategies.mean_reversion import generate_mean_reversion
from src.strategies.trend_continuation import generate_trend_continuation
from src.strategies.volatility_breakout import generate_volatility_breakout


STRATEGY_NAMES = ("trend_continuation", "mean_reversion", "volatility_breakout")


def _manual_attribution(series, name, generator):
    wf = run_walk_forward(series, BaselineConfig(), strategies=((name, generator),))
    return {
        "windows": len(wf),
        "windows_with_trades": sum(1 for r in wf if r["closed_trades"] > 0),
        "profitable_windows": sum(1 for r in wf if r["net_pnl"] > 0),
        "closed_trades": sum(r["closed_trades"] for r in wf),
        "total_net_pnl": sum(r["net_pnl"] for r in wf),
        "worst_window_net_pnl": min(r["net_pnl"] for r in wf),
        "best_window_net_pnl": max(r["net_pnl"] for r in wf),
        "windows_net_pnl": [round(r["net_pnl"], 6) for r in wf],
    }


def test_strategy_attribution_returns_one_entry_per_strategy():
    result = run_strategy_attribution(make_series(48))
    for name in STRATEGY_NAMES:
        assert name in result, f"missing attribution entry for {name}"
    entry = result["trend_continuation"]
    assert entry["windows"] >= 1
    assert entry["windows_with_trades"] >= 0
    assert entry["profitable_windows"] >= 0
    assert entry["closed_trades"] >= 0
    assert "total_net_pnl" in entry
    assert entry["worst_window_net_pnl"] <= entry["best_window_net_pnl"]


def test_strategy_attribution_never_selects_a_winner():
    result = run_strategy_attribution(make_series(48))
    # The whole point: this is measurement, not selection.
    assert result["selection_blocked"] is True
    assert "best_strategy" not in result
    assert "selected_strategy" not in result
    assert "promoted_strategy" not in result


def test_attribution_matches_independent_single_strategy_walk_forward():
    series = make_series(48)
    result = run_strategy_attribution(series)
    for name, generator in (
        ("trend_continuation", generate_trend_continuation),
        ("mean_reversion", generate_mean_reversion),
        ("volatility_breakout", generate_volatility_breakout),
    ):
        manual = _manual_attribution(series, name, generator)
        assert result[name] == manual, f"attribution for {name} diverged from direct walk-forward"


def test_attribution_reports_per_window_net_pnl_series():
    result = run_strategy_attribution(make_series(48))
    for name in STRATEGY_NAMES:
        assert len(result[name]["windows_net_pnl"]) == result[name]["windows"]


def test_single_strategy_walk_forward_runs_isolated_no_other_strategies():
    series = make_series(48)
    wf = run_walk_forward(series, BaselineConfig(), strategies=(("mean_reversion", generate_mean_reversion),))
    for row in wf:
        assert set(row["strategy_breakdown"]) == {"mean_reversion"}


def test_attribution_rejects_empty_snapshots_fail_closed():
    with pytest.raises(ValueError, match="strategy attribution"):
        run_strategy_attribution(())


def test_attribution_rejects_tampered_replay_data_fail_closed():
    series = make_series(48)
    tampered = replace(series[10], mark_price=series[10].mark_price + 5.0)
    broken = series[:10] + (tampered,) + series[11:]
    with pytest.raises(ValueError, match="evaluation data"):
        run_strategy_attribution(broken)
