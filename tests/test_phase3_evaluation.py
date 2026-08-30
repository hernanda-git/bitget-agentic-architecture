import pytest

from src.evaluation.baseline import BaselineConfig, run_baseline
from src.evaluation.stress import STRESS_DIMENSIONS, run_stress_matrix
from src.evaluation.statistics import compute_statistics
from src.evaluation.hypotheses import Hypothesis, HypothesisRegistry
from scripts.run_strategy_baseline import make_series


def test_stress_matrix_has_all_required_dimensions_and_no_added_trades():
    baseline = run_baseline(make_series())
    rows = run_stress_matrix(make_series(), BaselineConfig())
    assert set(STRESS_DIMENSIONS) <= {row["dimension"] for row in rows}
    required = {"closed_trades", "gross_pnl", "fees", "funding", "spread", "slippage", "net_pnl", "drawdown", "promotion_status"}
    assert all(required <= set(row) for row in rows)
    assert all(row["closed_trades"] <= baseline.closed_trades for row in rows)


def test_statistics_are_evidenced_and_fail_closed_below_minimum_sample():
    stats = compute_statistics([1.0, -0.5, 2.0, -1.0, 0.25], min_samples=5, bootstrap_samples=200, seed=7)
    assert stats["status"] == "EVIDENCED"
    assert stats["expectancy"] == pytest.approx(0.35)
    assert "bootstrap_ci" in stats and stats["profit_factor"] > 1
    assert "drawdown" in stats and "recovery" in stats
    assert "tail" in stats and "consecutive_losses" in stats
    sparse = compute_statistics([1.0, -1.0], min_samples=5)
    assert sparse["status"] == "NOT_EVIDENCED"
    assert sparse["reason"] == "MINIMUM_SAMPLE_NOT_MET"


def test_hypothesis_registry_requires_independent_reproducible_fields():
    registry = HypothesisRegistry()
    hypothesis = Hypothesis(
        hypothesis_id="H-001", title="Trend persistence", mechanism="momentum persists",
        data="offline candle history", features=("momentum",), category="time_structure",
        entry_exit="enter on breakout; exit at stop/target",
        cost_edge="move exceeds fees, spread and slippage", falsification="negative net PnL OOS",
        failure_modes="chop and stale data", data_exclusions="duplicates and incomplete windows",
        oos_gate="walk-forward positive net PnL with minimum sample",
    )
    registry.register(hypothesis)
    assert registry.as_dict()["hypotheses"][0]["hypothesis_id"] == "H-001"
    with pytest.raises(ValueError):
        registry.register(Hypothesis(hypothesis_id="bad", title="x"))
