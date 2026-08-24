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
