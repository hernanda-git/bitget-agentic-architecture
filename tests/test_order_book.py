"""TDD for observed order-book cost surface (read-only public depth) + fail-closed quality gate.

These tests are written BEFORE src/market/orderbook.py and src/market/orderbook_quality.py
exist. They must fail (ImportError / feature absent) on first run, then pass after GREEN.
The slice replaces the previously *assumed* half-spread in the cost model with an
*observed* top-of-book + depth surface, so walk-forward / cost-stress conclusions can be
calibrated against the live venue. Measurement only: nothing here changes the deterministic
promotion gate.
"""
import asyncio
import time

import httpx
import pytest

from src.market.bitget_public import BitgetPublicClient, PublicMarketError
from src.market.orderbook import OrderBook, OrderBookError, parse_order_book, top_spread_bps, mid_price, depth_within_bps
from src.market.orderbook_quality import OrderBookQuality, check_order_book


# A simple two-level book around mid 100.0 with a 0.1% top spread.
BOOK_PAYLOAD = {
    "code": "00000",
    "data": {
        "ts": "1000000",
        "bids": [["99.95", "1.0"], ["99.90", "2.0"], ["99.80", "3.0"]],
        "asks": [["100.05", "1.0"], ["100.10", "2.0"], ["100.20", "3.0"]],
    },
}


def test_parse_order_book_rejects_crossed_book():
    crossed = {"bids": [["101.0", "1.0"]], "asks": [["100.0", "1.0"]], "ts": "1000000"}
    with pytest.raises(OrderBookError):
        parse_order_book("BTCUSDT", crossed)


def test_parse_order_book_rejects_empty_or_nonpositive():
    with pytest.raises(OrderBookError):
        parse_order_book("BTCUSDT", {"bids": [], "asks": [], "ts": "1000000"})
    with pytest.raises(OrderBookError):
        parse_order_book("BTCUSDT", {"bids": [["100", "0"]], "asks": [["101", "1"]], "ts": "1000000"})


def test_top_spread_bps_computes_correctly():
    ob = parse_order_book("BTCUSDT", BOOK_PAYLOAD["data"], ts_ms=1_000_000)
    assert ob.bids[0][0] == 99.95
    assert ob.asks[0][0] == 100.05
    # mid 100.0, spread 0.10 -> 10 bps
    assert top_spread_bps(ob) == pytest.approx(10.0)
    assert mid_price(ob) == pytest.approx(100.0)


def test_depth_within_bps_sums_liquidity_each_side():
    ob = parse_order_book("BTCUSDT", BOOK_PAYLOAD["data"], ts_ms=1_000_000)
    # Within 60 bps of mid (mid 100, band = 0.6): bids 99.95/99.90/99.80 all inside (>=99.4);
    # asks 100.05/100.10/100.20 all inside (<=100.6).
    depth = depth_within_bps(ob, 60.0)
    assert depth["bid_depth"] == pytest.approx(6.0)
    assert depth["ask_depth"] == pytest.approx(6.0)
    assert depth["total_depth"] == pytest.approx(12.0)
    # Within 5 bps (band 0.05, range [99.95, 100.05]): only the top level on each side.
    tight = depth_within_bps(ob, 5.0)
    assert tight["bid_depth"] == pytest.approx(1.0)
    assert tight["ask_depth"] == pytest.approx(1.0)


def test_check_order_book_flags_crossed_book():
    crossed = OrderBook(symbol="BTCUSDT", bids=((101.0, 1.0),), asks=((100.0, 1.0),), ts_ms=1_000_000)
    q = check_order_book(crossed, now_ms=1_000_000)
    assert isinstance(q, OrderBookQuality)
    assert q.ok is False
    assert "CROSSED_BOOK" in q.reasons


def test_check_order_book_fails_closed_on_stale_and_empty():
    stale = parse_order_book("BTCUSDT", BOOK_PAYLOAD["data"], ts_ms=1_000_000)
    q_stale = check_order_book(stale, now_ms=1_000_000 + 120_000, max_age_ms=60_000)
    assert q_stale.ok is False
    assert "STALE_BOOK" in q_stale.reasons

    empty = OrderBook(symbol="BTCUSDT", bids=(), asks=(), ts_ms=1_000_000)
    q_empty = check_order_book(empty, now_ms=1_000_000)
    assert q_empty.ok is False
    assert "EMPTY_BIDS" in q_empty.reasons and "EMPTY_ASKS" in q_empty.reasons


def test_client_get_order_book_normalizes_via_mock():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=BOOK_PAYLOAD)
        if request.url.path.endswith("orderbook") else httpx.Response(404, json={})
    )
    client = BitgetPublicClient(transport=transport, min_interval_seconds=0)
    ob = asyncio.run(client.get_order_book("BTCUSDT", limit=20))
    assert isinstance(ob, OrderBook)
    assert ob.bids[0][0] == 99.95
    assert ob.asks[0][0] == 100.05
    assert ob.ts_ms == 1_000_000


def test_client_get_order_book_fail_closed_on_schema():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": "00000", "data": {"ts": "1"}})
    )
    client = BitgetPublicClient(transport=transport, min_interval_seconds=0)
    with pytest.raises(PublicMarketError, match="ORDERBOOK_SCHEMA|ORDERBOOK_VALUES"):
        asyncio.run(client.get_order_book("BTCUSDT", limit=20))
