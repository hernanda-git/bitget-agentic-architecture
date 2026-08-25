from dataclasses import asdict

from src.evaluation.baseline import BaselineConfig, run_baseline
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


def test_baseline_replay_is_reproducible_and_negative_gate_is_explicit():
    series = make_series()
    result = run_baseline(series, BaselineConfig(quantity=1.0, fee_bps=5, funding_bps=2, slippage_bps=2))
    again = run_baseline(series, BaselineConfig(quantity=1.0, fee_bps=5, funding_bps=2, slippage_bps=2))
    assert result == again
    assert result.network_calls == result.signed_calls == 0
    assert result.orders == 37
    assert result.closed_trades >= 0
    assert result.open_positions == 0
    assert result.end_of_replay_closes == 1
    assert result.fees >= 0 and result.funding >= 0
    assert set(result.strategy_breakdown) == {"trend_continuation", "mean_reversion", "volatility_breakout"}
    assert result.promotion_allowed is False
    assert result.promotion_reason in {"NEGATIVE_NET_PNL", "INCONCLUSIVE_NO_CLOSED_TRADES"}
    assert all(split["train_end"] < split["test_start"] for split in result.walk_forward_splits)
