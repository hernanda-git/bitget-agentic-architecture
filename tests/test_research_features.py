"""Phase 55 RED: causal, market-aware research features.

These tests define a small feature contract beyond the current textbook SMA /
momentum / volatility primitives. All features must use only candles available in
the snapshot and retain provenance through FeatureValue.
"""
from src.market.models import Candle, MarketSnapshot
from src.features.technical import build_features


def _snapshot(closes=(100.0, 101.0, 103.0, 102.0, 105.0), volumes=(10, 20, 30, 25, 40),
              funding=0.0005, oi=125.0):
    candles = tuple(
        Candle("1m", c - 0.5, max(c, (closes[i - 1] if i else c)) + 0.5,
               min(c, (closes[i - 1] if i else c)) - 0.5, c, volumes[i], 1_000 + i * 60_000)
        for i, c in enumerate(closes)
    )
    return MarketSnapshot("BTCUSDT", closes[-1], closes[-1] - 0.05, closes[-1] + 0.05,
                          funding, oi, 1_000 + (len(closes) - 1) * 60_000,
                          1_000 + (len(closes) - 1) * 60_000, candles).with_hash()


def test_build_features_exposes_causal_return_and_range_features():
    features = build_features(_snapshot())
    assert {"return_1", "return_3", "atr", "volume_zscore", "funding_rate", "open_interest"} <= features.keys()
    assert features["return_1"].value == (105.0 / 102.0) - 1
    assert features["return_3"].value == (105.0 / 101.0) - 1
    assert features["atr"].value > 0


def test_features_preserve_snapshot_provenance_and_version():
    snapshot = _snapshot()
    features = build_features(snapshot)
    for name in ("return_1", "return_3", "atr", "volume_zscore", "funding_rate", "open_interest", "open_interest_change"):
        value = features[name]
        assert value.source_snapshot_hash == snapshot.snapshot_hash
        assert value.source_timestamp == snapshot.source_ts_ms
        assert value.feature_version == "technical-v2"


def test_volume_zscore_is_neutral_with_insufficient_variation():
    features = build_features(_snapshot(volumes=(10, 10, 10, 10, 10)))
    assert features["volume_zscore"].value == 0.0


def test_optional_market_features_fail_closed_to_zero_when_unavailable():
    snapshot = _snapshot(funding=None, oi=None)
    features = build_features(snapshot)
    assert features["funding_rate"].value == 0.0
    assert features["open_interest"].value == 0.0
    assert features["open_interest_change"].value == 0.0


def test_features_do_not_use_future_candles():
    early = build_features(_snapshot(closes=(100.0, 101.0, 103.0)))
    later = build_features(_snapshot(closes=(100.0, 101.0, 103.0, 102.0, 105.0)))
    assert early["return_1"].value == (103.0 / 101.0) - 1
    assert early["return_1"].value != later["return_1"].value
