import pytest
from dataclasses import replace

from src.market.freshness import check_freshness
from src.market.models import Candle, MarketSnapshot
from src.market.snapshot_store import SnapshotStore


def snapshot(**overrides):
    values = dict(
        symbol="BTCUSDT", mark_price=64000, bid=63990, ask=64010,
        funding_rate=0.0001, open_interest=1000, observed_ts_ms=10000,
        source_ts_ms=10000, candles=(Candle("1m", 63900, 64100, 63800, 64000, 10, 10000),),
    )
    values.update(overrides)
    return MarketSnapshot(**values).with_hash()


def test_snapshot_hash_is_deterministic():
    assert snapshot().snapshot_hash == snapshot().snapshot_hash
    assert len(snapshot().snapshot_hash) == 64


def test_invalid_prices_and_candle_geometry_are_rejected():
    with pytest.raises(ValueError):
        snapshot(bid=64020)
    with pytest.raises(ValueError):
        Candle("1m", 10, 5, 1, 4, 1, 100)


def test_freshness_gate_rejects_stale_and_accepts_fresh():
    assert check_freshness(snapshot(), 10500, 3).ok
    assert check_freshness(snapshot(), 14001, 3).reason == "STALE_MARKET_DATA"


def test_hash_tampering_is_rejected():
    tampered = replace(snapshot(), snapshot_hash="bad")
    assert check_freshness(tampered, 10500, 3).reason == "SNAPSHOT_HASH_INVALID"


def test_store_rejects_timestamp_regression():
    store = SnapshotStore()
    store.put(snapshot(observed_ts_ms=10000, source_ts_ms=10000))
    with pytest.raises(ValueError, match="regression"):
        store.put(snapshot(observed_ts_ms=9999, source_ts_ms=9999))
