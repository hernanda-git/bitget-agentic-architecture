import pytest

import src.evaluation.stress as stress
from src.evaluation.baseline import BaselineConfig, run_baseline
from src.evaluation.stress import run_combined_stress
from scripts.run_strategy_baseline import make_series


def test_combined_stress_reports_worst_case_costs_and_is_blocked():
    """Combined adverse cost stress must report realistic multiplier-adjusted
    costs and never claim a promotion that the plain baseline did not earn."""
    baseline = run_baseline(make_series(), BaselineConfig())
    row = run_combined_stress(make_series(), BaselineConfig())

    assert row["dimension"] == "combined"
    assert row["fee_bps"] == pytest.approx(BaselineConfig().fee_bps * 1.5)
    assert row["funding_bps"] == pytest.approx(BaselineConfig().funding_bps * 2.0)
    assert row["slippage_bps"] == pytest.approx(BaselineConfig().slippage_bps * 1.5)
    # A combined adverse stress never unblocks the deterministic promotion gate.
    assert row["promotion_allowed"] is False
    assert row["promotion_status"] == "BLOCKED"
    # Every row carries the cost-inclusive outcome fields for the report.
    for key in ("closed_trades", "gross_pnl", "fees", "funding", "spread", "slippage", "net_pnl", "drawdown"):
        assert key in row


def test_combined_stress_never_adds_trades_versus_baseline():
    """Fail-closed invariant: raising costs can only skip trades, never invent
    them. If this ever fails, a cost-modeling bug is inflating survivorship."""
    baseline = run_baseline(make_series(), BaselineConfig())
    row = run_combined_stress(make_series(), BaselineConfig())
    assert row["closed_trades"] <= baseline.closed_trades
    assert row["baseline_closed_trades"] == baseline.closed_trades


def test_combined_stress_applies_distinct_realistic_multipliers():
    """The three cost axes move together but at realistic, distinct rates
    (funding spikes harder than fees/slippage in adverse regimes)."""
    row = run_combined_stress(make_series(), BaselineConfig(),
                              fee_mult=2.0, funding_mult=3.0, slippage_mult=2.0)
    cfg = BaselineConfig()
    assert row["fee_bps"] == pytest.approx(cfg.fee_bps * 2.0)
    assert row["funding_bps"] == pytest.approx(cfg.funding_bps * 3.0)
    assert row["slippage_bps"] == pytest.approx(cfg.slippage_bps * 2.0)
    # Distinct multipliers must scale the three cost axes independently, so the
    # resulting per-axis costs are pairwise distinct (no two axes silently collapse).
    assert len({row["fee_bps"], row["funding_bps"], row["slippage_bps"]}) == 3


def test_combined_stress_pipeline_invariant_on_real_dataset():
    """On real stored public history, the combined adverse stress must keep the
    deterministic promotion gate BLOCKED and must not add trades. This is the
    fail-closed invariant that protects the negative baseline from a cost-modeling
    regression that could silently 'improve' results under stress."""
    from pathlib import Path
    from src.market.history import load_dataset, snapshots_from_dataset
    from src.evaluation.baseline import run_walk_forward, gate_walk_forward_robustness

    dataset = load_dataset(Path("data/history/BTCUSDT_1m.json"))
    snapshots = snapshots_from_dataset(dataset)
    config = BaselineConfig(real_funding=True)

    baseline = run_baseline(snapshots, config)
    combined = run_combined_stress(snapshots, config)

    assert combined["closed_trades"] <= baseline.closed_trades
    assert combined["promotion_allowed"] is False
    assert combined["promotion_status"] == "BLOCKED"

    # The deterministic promotion gate is independent of stress and stays blocked.
    walk_forward = run_walk_forward(snapshots, config)
    gate = gate_walk_forward_robustness(walk_forward, trade_pnls=baseline.trade_pnls,
                                        min_closed_trades=30)
    assert gate["selection_blocked"] is True
    assert gate["expectancy_positive_with_ci"] is False
