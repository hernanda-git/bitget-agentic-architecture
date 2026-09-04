"""RED tests for the order-flow impulse hypothesis.

Uses close_location_value, volume_pressure, market_impact_proxy, spread_proxy,
and a configurable holding period to generate a directional impulse candidate.
"""
from src.strategies.orderflow_impulse import generate_orderflow_impulse
from src.market.models import Candle, MarketSnapshot
from src.strategies.base import CostAssumptions


def _make_snapshot(last_candle, volumes, *, spread_bps=2.0):
    """Build a snapshot with a controlled last candle."""
    ts = 1_700_000_000_000
    n = len(volumes)
    candles = []
    for i in range(n - 1):
        candles.append(Candle("1m", 100.0, 100.5, 99.5, 100.0, volumes[i], ts + i * 60_000))
    candles.append(last_candle)
    price = last_candle.close
    spread = price * spread_bps / 10_000
    return MarketSnapshot("BTCUSDT", price, price - spread, price + spread,
                          0.0005, 100, ts + (n - 1) * 60_000,
                          ts + (n - 1) * 60_000, candles=candles).with_hash()


def _bullish_candle():
    return Candle("1m", 100.0, 101.0, 99.0, 100.8, 100, 1_700_000_000_000)


def _bearish_candle():
    return Candle("1m", 101.0, 102.0, 100.0, 100.2, 100, 1_700_000_000_000)


def _volumes(n, last_mult=10):
    return [10] * (n - 1) + [10 * last_mult]


def _clv_bearish_body_candle():
    """CLV > 0.5 (bullish) but bearish body (close < open)."""
    return Candle("1m", 101.5, 102.0, 99.0, 101.0, 100, 1_700_000_000_000)


def test_bullish_orderflow_emits_long_candidate():
    c = generate_orderflow_impulse(
        _make_snapshot(_bullish_candle(), _volumes(20)),
        CostAssumptions(),
    )[0]
    assert c.side == "BUY"
    assert c.stop_loss < c.entry < c.take_profit
    assert c.strategy_version == "orderflow-v1"
    assert c.regime == "ORDERFLOW_IMPULSE"


def test_bearish_orderflow_emits_short_candidate():
    c = generate_orderflow_impulse(
        _make_snapshot(_bearish_candle(), _volumes(20)),
        CostAssumptions(),
    )[0]
    assert c.side == "SELL"
    assert c.stop_loss > c.entry > c.take_profit
    assert c.strategy_version == "orderflow-v1"


def test_weak_orderflow_clv_deviation_is_rejected():
    weak_candle = Candle("1m", 100.0, 101.0, 99.0, 100.0, 100, 1_700_000_000_000)
    assert generate_orderflow_impulse(
        _make_snapshot(weak_candle, _volumes(20)),
        CostAssumptions(),
    ) == []


def test_market_impact_must_confirm_direction():
    """Market impact (body direction) must confirm CLV signal."""
    assert generate_orderflow_impulse(
        _make_snapshot(_clv_bearish_body_candle(), _volumes(20)),
        CostAssumptions(),
    ) == []


def test_high_spread_rejects_candidate():
    c = generate_orderflow_impulse(
        _make_snapshot(_bullish_candle(), _volumes(20), spread_bps=50.0),
        CostAssumptions(),
    )
    assert c == []


def test_cost_gate_rejects_when_costs_exceed_move():
    assert generate_orderflow_impulse(
        _make_snapshot(_bullish_candle(), _volumes(20)),
        CostAssumptions(fee_bps=100, slippage_bps=100, funding_bps=100),
    ) == []


def test_candidate_provenance_is_deterministic_and_causal():
    snap = _make_snapshot(_bullish_candle(), _volumes(20))
    a = generate_orderflow_impulse(snap, CostAssumptions())[0]
    b = generate_orderflow_impulse(snap, CostAssumptions())[0]
    assert a == b
    assert a.feature_snapshot_hash == snap.snapshot_hash
    assert a.expiry > snap.source_ts_ms


def test_expiry_matches_holding_period():
    from src.strategies.orderflow_impulse import HOLDING_PERIOD_BARS, EXPIRY_MS
    snap = _make_snapshot(_bullish_candle(), _volumes(20))
    c = generate_orderflow_impulse(snap, CostAssumptions())[0]
    assert c.expiry == snap.source_ts_ms + EXPIRY_MS
    assert EXPIRY_MS == HOLDING_PERIOD_BARS * 60_000
