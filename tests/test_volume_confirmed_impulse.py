"""RED tests for the pre-registered volume-confirmed impulse hypothesis."""
from src.market.models import Candle, MarketSnapshot
from src.strategies.base import CostAssumptions
from src.strategies.volume_confirmed_impulse import generate_volume_confirmed_impulse


def snapshot(closes, volumes):
    ts = 1_700_000_000_000
    candles = tuple(Candle("1m", min(c, closes[i - 1] if i else c) - .1,
                           max(c, closes[i - 1] if i else c) + .1,
                           min(c, closes[i - 1] if i else c) - .2, c, volumes[i],
                           ts + i * 60_000) for i, c in enumerate(closes))
    price = closes[-1]
    return MarketSnapshot("BTCUSDT", price, price - .01, price + .01, 0.0001, 100,
                          candles[-1].source_ts_ms, candles[-1].source_ts_ms,
                          candles=candles).with_hash()


def test_positive_impulse_with_volume_confirmation_emits_long_candidate():
    c = generate_volume_confirmed_impulse(
        snapshot([100, 100.2, 100.1, 100.3, 101.5], [10, 10, 10, 10, 100]),
        CostAssumptions(),
    )[0]
    assert c.side == "BUY"
    assert c.stop_loss < c.entry < c.take_profit
    assert c.strategy_version == "volume-impulse-v1"


def test_negative_impulse_with_volume_confirmation_emits_short_candidate():
    c = generate_volume_confirmed_impulse(
        snapshot([100, 99.8, 99.9, 99.7, 98.5], [10, 10, 10, 10, 100]),
        CostAssumptions(),
    )[0]
    assert c.side == "SELL"
    assert c.stop_loss > c.entry > c.take_profit


def test_impulse_without_unusual_volume_is_rejected():
    assert generate_volume_confirmed_impulse(
        snapshot([100, 100.2, 100.1, 100.3, 101.5], [10, 11, 9, 10, 11]),
        CostAssumptions(),
    ) == []


def test_cost_gate_rejects_impulse_when_costs_exceed_fixed_move():
    assert generate_volume_confirmed_impulse(
        snapshot([100, 100.01, 100.0, 100.01, 100.02], [10, 10, 10, 10, 100]),
        CostAssumptions(fee_bps=100, slippage_bps=100, funding_bps=100),
    ) == []


def test_candidate_provenance_is_deterministic_and_causal():
    s = snapshot([100, 100.2, 100.1, 100.3, 101.5], [10, 10, 10, 10, 100])
    a = generate_volume_confirmed_impulse(s, CostAssumptions())[0]
    b = generate_volume_confirmed_impulse(s, CostAssumptions())[0]
    assert a == b
    assert a.feature_snapshot_hash == s.snapshot_hash
    assert a.expiry > s.source_ts_ms
