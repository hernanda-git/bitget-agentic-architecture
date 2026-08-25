import asyncio
import json

import httpx
import pytest

from src.market.bitget_public import BitgetPublicClient, PublicMarketError


TICKER = {
    "code": "00000",
    "data": [{"lastPr": "64000", "bidPr": "63990", "askPr": "64010", "ts": "10000"}],
}
CANDLES = {"code": "00000", "data": [["10000", "63900", "64100", "63800", "64000", "10"]]}


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("ticker"):
        return httpx.Response(200, json=TICKER)
    if request.url.path.endswith("candles"):
        return httpx.Response(200, json=CANDLES)
    return httpx.Response(404, json={})


def test_public_adapter_has_no_auth_header_and_normalizes_snapshot():
    seen = []

    def capture(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        return handler(request)

    client = BitgetPublicClient(transport=httpx.MockTransport(capture), min_interval_seconds=0)
    result = asyncio.run(client.fetch_snapshot("BTCUSDT", observed_ts_ms=10000))
    assert result.symbol == "BTCUSDT"
    assert result.mark_price == 64000
    assert result.snapshot_hash
    assert all("authorization" not in headers for headers in seen)


def test_public_api_error_is_fail_closed():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"code": "40001", "data": []}))
    client = BitgetPublicClient(transport=transport, min_interval_seconds=0)
    with pytest.raises(PublicMarketError, match="PUBLIC_API_ERROR"):
        asyncio.run(client.fetch_ticker("BTCUSDT"))


def test_rate_limit_is_explicit():
    transport = httpx.MockTransport(lambda request: httpx.Response(429, json={}))
    client = BitgetPublicClient(transport=transport, min_interval_seconds=0)
    with pytest.raises(PublicMarketError, match="PUBLIC_RATE_LIMIT"):
        asyncio.run(client.fetch_ticker("BTCUSDT"))


def test_ticker_validation_accepts_positive_mark_outside_spread_and_rejects_invalid_values():
    valid_outside_spread = {
        "lastPr": "80223.3",
        "markPrice": "80223.3",
        "bidPr": "80224",
        "askPr": "80224.1",
        "ts": "10000",
    }
    client = BitgetPublicClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": "00000", "data": [valid_outside_spread]})),
        min_interval_seconds=0,
    )
    ticker = asyncio.run(client.fetch_ticker("BTCUSDT"))
    assert ticker["mark_price"] == 80223.3
    assert ticker["bid"] == 80224.0
    assert ticker["ask"] == 80224.1

    invalid_tickers = [
        ({**valid_outside_spread, "bidPr": "80225", "askPr": "80224"}, "TICKER_IMPOSSIBLE_PRICES"),
        ({**valid_outside_spread, "bidPr": "0"}, "TICKER_IMPOSSIBLE_PRICES"),
        ({**valid_outside_spread, "askPr": "-1"}, "TICKER_IMPOSSIBLE_PRICES"),
        ({**valid_outside_spread, "markPrice": "not-a-number"}, "TICKER_VALUES"),
    ]
    for row, error in invalid_tickers:
        transport = httpx.MockTransport(lambda request, row=row: httpx.Response(200, json={"code": "00000", "data": [row]}))
        client = BitgetPublicClient(transport=transport, min_interval_seconds=0)
        with pytest.raises(PublicMarketError, match=error):
            asyncio.run(client.fetch_ticker("BTCUSDT"))
