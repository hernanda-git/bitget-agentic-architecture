import asyncio
import json
from pathlib import Path

import httpx
import pytest

from src.market.bitget_public import BitgetPublicClient, PublicMarketError
from src.market.models import Candle, MarketSnapshot


def test_client_requires_explicit_venue_and_product_type():
    with pytest.raises(ValueError, match="venue"):
        BitgetPublicClient(product_type="USDT-FUTURES")
    with pytest.raises(ValueError, match="product"):
        BitgetPublicClient(venue="bitget", product_type="SPOT")


def test_client_retries_bounded_and_records_metrics_without_auth():
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) < 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"code": "00000", "data": [{"lastPr": "10", "bidPr": "9.9", "askPr": "10.1", "ts": "10000", "baseVol": "2"}]})
    client = BitgetPublicClient(venue="bitget", product_type="USDT-FUTURES", transport=httpx.MockTransport(handler),
                                min_interval_seconds=0, max_retries=1, backoff_seconds=0)
    result = asyncio.run(client.fetch_ticker("BTCUSDT"))
    assert result["volume"] == 2.0
    assert client.metrics.requests == 2
    assert client.metrics.failures == 1
    assert all("authorization" not in r.headers for r in calls)


def test_snapshot_requires_complete_windows_and_has_normalized_metadata():
    candle = Candle("1m", 10, 11, 9, 10.5, 2, 10000)
    snapshot = MarketSnapshot(symbol="BTCUSDT", mark_price=10.5, bid=10, ask=11,
        funding_rate=0.001, open_interest=3, volume=2, observed_ts_ms=10000,
        source_ts_ms=10000, candles=(candle,), candles_by_window={"1m": (candle,)},
        feature_version="market-v1").with_hash()
    assert snapshot.spread == 1
    assert snapshot.freshness_ms == 0
    assert snapshot.snapshot_hash == snapshot.computed_hash()
    with pytest.raises(ValueError, match="incomplete"):
        MarketSnapshot(symbol="BTCUSDT", mark_price=10, bid=9, ask=11, funding_rate=0,
            open_interest=1, volume=1, observed_ts_ms=10000, source_ts_ms=10000,
            candles=(), required_windows=("1m",))


def test_public_shadow_script_is_distinct_and_never_signed(tmp_path):
    from scripts.run_public_shadow import run_public_shadow
    report = asyncio.run(run_public_shadow(1, ["BTCUSDT"], tmp_path / "ledger.sqlite3", tmp_path / "reports",
                                           client_factory=lambda: None, provider=None))
    assert report["mode"] == "public-shadow"
    assert report["signed_calls"] == 0
    assert report["orders_placed"] == 0
    assert "freshness_distribution" in report
