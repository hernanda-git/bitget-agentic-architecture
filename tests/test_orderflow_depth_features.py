"""Phase 56 RED: historical order-flow/depth proxy features + holding-period labels.

These tests define a feature contract beyond the current v2 primitives:
depth/order-flow proxies derived from candle geometry and volume, plus a
proper label function that looks ahead by a configurable holding period
instead of a single bar.
"""
import pytest
from src.features.technical import build_features, make_holding_period_labels
from src.market.models import Candle, MarketSnapshot


def _snapshot(closes, volumes=None, *, funding=0.0005, oi=100.0):
    """Build a snapshot with explicit OHLCV candles."""
    if volumes is None:
        volumes = [100] * len(closes)
    candles = tuple(
        Candle("1m", c - 0.5, max(c, (closes[i - 1] if i else c)) + 0.5,
               min(c, (closes[i - 1] if i else c)) - 0.5, c, volumes[i], 1_000 + i * 60_000)
        for i, c in enumerate(closes)
    )
    return MarketSnapshot("BTCUSDT", closes[-1], closes[-1] - 0.05, closes[-1] + 0.05,
                          funding, oi, 1_000 + (len(closes) - 1) * 60_000,
                          1_000 + (len(closes) - 1) * 60_000, candles).with_hash()


# ---- Order-flow / depth proxy features ----

def test_close_location_value_proxy_computes_position_in_range():
    """CLV = (close - low) / (high - low): 1.0 at bar high, 0.0 at bar low."""
    snap = _snapshot([100.0, 101.0, 103.0, 102.0, 102.5])
    f = build_features(snap)
    assert "close_location_value" in f
    assert 0.0 <= f["close_location_value"].value <= 1.0


def test_volume_pressure_proxy_sign_matches_clv_direction():
    """Volume pressure = CLV * normalized volume; sign tracks CLV."""
    snap_up = _snapshot([100.0, 101.0, 103.0, 104.0, 104.5], volumes=[10, 10, 10, 10, 10])
    snap_down = _snapshot([104.5, 104.0, 103.0, 101.0, 100.0], volumes=[10, 10, 10, 10, 10])
    up_clv = build_features(snap_up)["close_location_value"].value
    dn_clv = build_features(snap_down)["close_location_value"].value
    up_vp = build_features(snap_up)["volume_pressure"].value
    dn_vp = build_features(snap_down)["volume_pressure"].value
    assert (up_vp > 0) == (up_clv > 0.5)
    assert (dn_vp < 0) == (dn_clv < 0.5)


def test_market_impact_proxy_body_to_range_ratio():
    """Market impact proxy = (close - open) / (high - low): positive bullish body."""
    snap = _snapshot([100.0, 101.0, 102.0, 103.0, 104.0])
    f = build_features(snap)
    assert "market_impact_proxy" in f
    assert f["market_impact_proxy"].value > 0  # monotonically rising candles


def test_spread_proxy_returns_observed_spread_in_bps():
    """Spread proxy uses the assumed_half_spread_bps from the snapshot."""
    snap = _snapshot([100.0, 101.0, 102.0, 103.0, 104.0])
    f = build_features(snap)
    assert "spread_proxy" in f
    assert f["spread_proxy"].value > 0


def test_orderflow_features_preserve_provenance_and_version():
    """Order-flow proxy features carry technical-v2 provenance."""
    snap = _snapshot([100.0, 101.0, 102.0, 103.0, 104.0])
    f = build_features(snap)
    for name in ("close_location_value", "volume_pressure", "market_impact_proxy", "spread_proxy"):
        assert name in f
        assert f[name].feature_version == "technical-v2"
        assert f[name].source_snapshot_hash == snap.snapshot_hash
        assert f[name].source_timestamp == snap.source_ts_ms


def test_close_location_value_neutral_when_flat_bar():
    """Flat OHLC bar => CLV = 0.5 (midpoint), not an artificial signal."""
    flat_close = 100.0
    candles = tuple(
        Candle("1m", flat_close, flat_close + 0.5, flat_close - 0.5, flat_close, 10, 1_000 + i * 60_000)
        for i in range(5)
    )
    snap = MarketSnapshot("BTCUSDT", flat_close, flat_close - 0.05, flat_close + 0.05,
                          0.0005, 100, 3_000_000, 3_000_000, candles).with_hash()
    f = build_features(snap)
    assert f["close_location_value"].value == 0.5


# ---- Holding-period labels ----

def test_holding_period_labels_look_ahead_by_n_bars():
    """Labels = forward return over `period` bars, not just the next bar."""
    closes = [100.0, 101.0, 102.0, 103.0, 105.0, 107.0]
    labels = make_holding_period_labels(closes, period=2)
    # Label for bar i = closes[i+period] / closes[i] - 1
    assert len(labels) == len(closes) - 2
    assert labels[0]["forward_return"] == pytest.approx(102.0 / 100.0 - 1)  # 100 -> 102 over 2 bars
    assert labels[1]["forward_return"] == pytest.approx(103.0 / 101.0 - 1)  # 101 -> 103 over 2 bars


def test_holding_period_labels_insufficient_history_returns_empty():
    """Not enough bars for the holding period => no labels."""
    labels = make_holding_period_labels([100.0, 101.0], period=3)
    assert labels == []


def test_holding_period_labels_zero_period_raises():
    """Period must be positive."""
    with pytest.raises(ValueError):
        make_holding_period_labels([100.0, 101.0], period=0)


def test_holding_period_labels_preserved_provenance():
    """Labels include source timestamps and symbol provenance."""
    closes = [100.0, 101.0, 102.0, 103.0, 105.0]
    labels = make_holding_period_labels(closes, period=2)
    assert len(labels) == 3
    for label in labels:
        assert label["forward_return"] is not None
        assert "entry_ts_ms" in label
        assert "exit_ts_ms" in label
        assert "symbol" in label


def test_holding_period_labels_negative_forward_return():
    """Labels correctly capture losing holding periods."""
    closes = [105.0, 103.0, 100.0, 98.0, 95.0]
    labels = make_holding_period_labels(closes, period=2)
    assert len(labels) == 3
    assert labels[0]["forward_return"] == pytest.approx(100.0 / 105.0 - 1)  # negative
    assert labels[0]["forward_return"] < 0


# ---- Mutation guard: features are causal (no future data) ----

def test_orderflow_features_are_causal_no_future_candles():
    """Order-flow proxies must use only current and past candles."""
    early = _snapshot([100.0, 101.0, 102.0, 103.0, 104.0])
    later = _snapshot([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])
    early_clv = build_features(early)["close_location_value"].value
    later_clv = build_features(later)["close_location_value"].value
    # First 5 candles identical => same CLV for the 5th bar
    assert early_clv == later_clv
