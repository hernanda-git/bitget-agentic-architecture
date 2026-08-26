from dataclasses import asdict, replace

import pytest

from src.evaluation.baseline import (
    BaselineConfig,
    run_baseline,
    run_walk_forward,
    run_cost_stress,
    summarize_walk_forward,
)
from src.features.registry import FeatureValue
from src.features.technical import build_features
from src.market.models import Candle, MarketSnapshot
from src.strategies.base import CostAssumptions
from src.strategies.mean_reversion import generate_mean_reversion
from src.strategies.regime import Regime, classify_regime
from src.strategies.trend_continuation import generate_trend_continuation
from src.strategies.volatility_breakout import generate_volatility_breakout
from scripts.run_strategy_baseline import make_series


def candles(closes, start=1_700_000_000_000):
    return tuple(Candle("1m", c - 0.5, c + 1, c - 1, c, 10, start + i * 60_000) for i, c in enumerate(closes))


def snapshot(closes, *, funding=0.0001, spread=0.2, ts=None):
    cs = candles(closes)
    mark = closes[-1]
    ts = ts or cs[-1].source_ts_ms
    return MarketSnapshot("BTCUSDT", mark, mark - spread / 2, mark + spread / 2, funding, 100,
                          ts, cs[-1].source_ts_ms, candles=cs, snapshot_hash="").with_hash()


def test_feature_values_are_versioned_and_hash_stable():
    s = snapshot([100, 101, 102, 103, 104])
    values = build_features(s)
    assert values
    assert all(isinstance(v, FeatureValue) for v in values.values())
    item = values["sma"]
    assert (item.feature_name, item.feature_version, item.source_snapshot_hash, item.source_timestamp,
            item.parameters, item.value) == ("sma", "technical-v1", s.snapshot_hash, s.source_ts_ms,
                                               {"window": 3}, 103.0)
    assert build_features(s)["sma"] == item


def test_candidate_generators_emit_complete_cost_gated_candidates():
    s = snapshot([100, 101, 102, 103, 104, 106], spread=0.02)
    costs = CostAssumptions(fee_bps=5, funding_bps=1, slippage_bps=2)
    generators = [generate_trend_continuation, generate_mean_reversion, generate_volatility_breakout]
    for generator in generators:
        candidates = generator(s, costs)
        for candidate in candidates:
            data = asdict(candidate)
            assert set(("candidate_id", "strategy_name", "strategy_version", "symbol", "side", "entry",
                        "stop_loss", "take_profit", "expiry", "feature_snapshot_hash", "expected_cost",
                        "minimum_required_edge")) <= data.keys()
            assert candidate.feature_snapshot_hash == s.snapshot_hash
            assert candidate.expected_move > candidate.expected_cost
            assert candidate.minimum_required_edge >= candidate.expected_cost


def test_regime_classification_is_deterministic_and_fail_closed():
    assert classify_regime(snapshot([100, 101, 102, 103, 104, 105])) == Regime.TRENDING
    assert classify_regime(snapshot([100, 100.1, 99.9, 100.05, 99.95])) == Regime.RANGING
    assert classify_regime(snapshot([100, 120, 80, 125, 75])) == Regime.HIGH_VOLATILITY
    degraded = snapshot([100, 101, 102])
    assert classify_regime(degraded, minimum_candles=10) == Regime.DATA_DEGRADED
    liquidation = snapshot([100, 100.5, 99, 70, 71])
    assert classify_regime(liquidation) == Regime.LIQUIDATION_EVENT


def test_baseline_never_stacks_overlapping_entries_for_one_strategy():
    # Every snapshot shows a persistent breakout condition (flat price at a
    # range high) and the resulting stop/target band is never touched, so each
    # simulated position stays open until end of replay. A real bot holds one
    # position per strategy: later signals while a position is open must not
    # stack additional overlapping entries.
    seqs = [[206] * (i + 1) for i in range(12)]
    series = tuple(snapshot(s, spread=0.02) for s in seqs)
    result = run_baseline(series, BaselineConfig(quantity=1.0, fee_bps=5, funding_bps=2, slippage_bps=2))
    assert result.strategy_breakdown["volatility_breakout"]["closed_trades"] == 1
    assert result.closed_trades == 1
    assert result.open_positions == 0


def test_baseline_replay_is_reproducible_and_negative_gate_is_explicit():
    series = make_series()
    result = run_baseline(series, BaselineConfig(quantity=1.0, fee_bps=5, funding_bps=2, slippage_bps=2))
    again = run_baseline(series, BaselineConfig(quantity=1.0, fee_bps=5, funding_bps=2, slippage_bps=2))
    assert result == again
    assert result.network_calls == result.signed_calls == 0
    assert result.orders == 16
    assert result.closed_trades >= 0
    assert result.open_positions == 0
    assert result.end_of_replay_closes == 1
    assert result.protection_attachments == result.closed_trades
    assert result.reconciliation_checks == 0
    assert result.fees >= 0 and result.funding >= 0
    assert set(result.strategy_breakdown) == {"trend_continuation", "mean_reversion", "volatility_breakout"}
    assert result.promotion_allowed is False
    assert result.promotion_reason in {"NEGATIVE_NET_PNL", "INCONCLUSIVE_NO_CLOSED_TRADES"}
    assert all(split["train_end"] < split["test_start"] for split in result.walk_forward_splits)


def test_baseline_charges_final_spread_on_end_of_replay_close():
    result = run_baseline(
        make_series(),
        BaselineConfig(quantity=1.0, fee_bps=0, funding_bps=0, slippage_bps=0),
    )

    assert result.end_of_replay_closes == 1
    assert result.spread == pytest.approx(0.30)


def test_baseline_exposes_gross_pnl_and_explicit_cost_attribution():
    result = run_baseline(make_series())
    assert result.gross_pnl == sum(row["gross_pnl"] for row in result.strategy_breakdown.values())
    assert result.net_pnl == result.gross_pnl - result.fees - result.spread - result.slippage - result.funding
    assert result.spread >= 0
    assert all("gross_pnl" in row for row in result.strategy_breakdown.values())
    assert all("spread" in row for row in result.strategy_breakdown.values())


def test_walk_forward_evaluation_has_disjoint_embargoed_test_windows():
    evaluation = run_walk_forward(make_series(48), BaselineConfig(train_fraction=0.5, embargo=2, test_window=10))
    assert len(evaluation) >= 2
    assert all(item["train_end"] < item["test_start"] for item in evaluation)
    assert all(item["test_end"] - item["test_start"] + 1 == 10 for item in evaluation)
    assert all(evaluation[i]["test_end"] < evaluation[i + 1]["test_start"] for i in range(len(evaluation) - 1))
    assert all(item["context_start"] == 0 for item in evaluation)
    assert all(item["context_end"] == item["test_start"] - 1 for item in evaluation)
    assert all(item["test_snapshots"] == 10 for item in evaluation)
    assert all(set(item["strategy_breakdown"]) == {"trend_continuation", "mean_reversion", "volatility_breakout"}
               for item in evaluation)


def test_walk_forward_reports_slippage_and_net_pnl_formula():
    evaluation = run_walk_forward(make_series(36), BaselineConfig(train_fraction=0.6, embargo=1, test_window=10))
    row = evaluation[0]
    assert row["slippage"] >= 0
    assert row["net_pnl"] == row["gross_pnl"] - row["fees"] - row["spread"] - row["slippage"] - row["funding"]


def test_funding_received_offsets_funding_paid_in_cost_attribution():
    from src.evaluation.baseline import _funding_cost

    assert _funding_cost({"funding_paid": 3.0, "funding_received": 1.25}) == 1.75


def test_cost_stress_reports_degradation_without_changing_baseline():
    base = run_baseline(make_series())
    stress = run_cost_stress(make_series(), BaselineConfig(), (1.0, 2.0))
    assert stress[0]["net_pnl"] == base.net_pnl
    assert stress[0]["slippage"] == base.slippage
    assert stress[0]["net_pnl"] == (stress[0]["gross_pnl"] - stress[0]["fees"]
                                     - stress[0]["spread"] - stress[0]["slippage"] - stress[0]["funding"])
    assert stress[1]["net_pnl"] <= stress[0]["net_pnl"]
    assert stress[1]["fee_bps"] == 10.0
    assert stress[1]["funding"] > stress[0]["funding"]
    assert stress[1]["funding"] == 2 * stress[0]["funding"]
    assert stress[1]["slippage"] > stress[0]["slippage"]


def test_walk_forward_rejects_invalid_evaluation_parameters():
    series = make_series(12)
    for config in (
        BaselineConfig(train_fraction=0),
        BaselineConfig(train_fraction=1),
        BaselineConfig(embargo=-1),
        BaselineConfig(test_window=0),
    ):
        with pytest.raises(ValueError, match="walk-forward"):
            run_walk_forward(series, config)


def test_walk_forward_rejects_series_without_a_complete_test_window():
    with pytest.raises(ValueError, match="walk-forward"):
        run_walk_forward(make_series(6), BaselineConfig(train_fraction=0.8, embargo=1, test_window=3))


def test_walk_forward_excludes_incomplete_trailing_window():
    evaluation = run_walk_forward(make_series(36), BaselineConfig(train_fraction=0.6, embargo=1, test_window=10))
    assert len(evaluation) == 1
    assert evaluation[0]["test_start"] == 22
    assert evaluation[0]["test_end"] == 31
    assert evaluation[0]["test_snapshots"] == 10


def test_cost_stress_rejects_non_positive_or_non_finite_multipliers():
    series = make_series(12)
    for multipliers in ((0.0,), (-1.0,), (float("nan"),), (float("inf"),)):
        with pytest.raises(ValueError, match="cost-stress"):
            run_cost_stress(series, multipliers=multipliers)


def test_summarize_walk_forward_reports_window_robustness_facts():
    evaluation = run_walk_forward(make_series(48), BaselineConfig(train_fraction=0.5, embargo=2, test_window=10))
    summary = summarize_walk_forward(evaluation)
    assert summary["windows"] == len(evaluation) >= 2
    assert summary["windows_with_trades"] == sum(1 for r in evaluation if r["closed_trades"] > 0)
    assert summary["profitable_windows"] == sum(1 for r in evaluation if r["net_pnl"] > 0)
    assert summary["closed_trades"] == sum(r["closed_trades"] for r in evaluation)
    assert summary["total_net_pnl"] == pytest.approx(sum(r["net_pnl"] for r in evaluation))
    assert summary["worst_window_net_pnl"] == min(r["net_pnl"] for r in evaluation)
    assert summary["best_window_net_pnl"] == max(r["net_pnl"] for r in evaluation)


def test_summarize_walk_forward_rejects_empty_rows_fail_closed():
    with pytest.raises(ValueError, match="walk-forward summary"):
        summarize_walk_forward(())


def test_baseline_rejects_snapshot_hash_mismatch_before_replay():
    series = make_series(12)
    tampered = replace(series[5], mark_price=series[5].mark_price + 1.0)

    with pytest.raises(ValueError, match="evaluation data.*snapshot hash"):
        run_baseline(series[:5] + (tampered,) + series[6:])


def test_baseline_rejects_timestamp_regression_in_input_order():
    series = make_series(12)
    reordered = series[:8] + (series[9], series[8]) + series[10:]

    with pytest.raises(ValueError, match="evaluation data.*timestamp"):
        run_baseline(reordered)


def test_baseline_rejects_source_timestamp_regression_when_observed_order_is_valid():
    series = make_series(12)
    malformed = replace(series[8], source_ts_ms=series[7].source_ts_ms - 1).with_hash()

    with pytest.raises(ValueError, match="evaluation data.*timestamp"):
        run_baseline(series[:8] + (malformed,) + series[9:])


def test_baseline_rejects_mixed_symbol_replay_data_even_when_rehashed():
    series = make_series(12)
    mixed = replace(series[5], symbol="ETHUSDT").with_hash()

    with pytest.raises(ValueError, match="evaluation data.*symbol"):
        run_baseline(series[:5] + (mixed,) + series[6:])


def test_walk_forward_rejects_reordered_candle_history_even_when_rehashed():
    series = make_series(36)
    current = series[22]
    malformed = replace(
        current,
        candles=current.candles[:-2] + (current.candles[-1], current.candles[-2]),
    ).with_hash()

    with pytest.raises(ValueError, match="evaluation data.*candle.*timestamp"):
        run_walk_forward(series[:22] + (malformed,) + series[23:],
                         BaselineConfig(train_fraction=0.6, embargo=1, test_window=10))


def test_walk_forward_rejects_reordered_candle_window_history_even_when_rehashed():
    series = make_series(36)
    current = series[22]
    malformed = replace(
        current,
        candles_by_window={"1m": tuple(reversed(current.candles))},
        required_windows=("1m",),
    ).with_hash()

    with pytest.raises(ValueError, match="evaluation data.*candle.*timestamp"):
        run_walk_forward(series[:22] + (malformed,) + series[23:],
                         BaselineConfig(train_fraction=0.6, embargo=1, test_window=10))
