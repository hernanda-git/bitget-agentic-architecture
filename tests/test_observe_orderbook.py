"""TDD for the live observed order-book calibration collector (scripts/observe_orderbook.py).

Written BEFORE ``scripts/observe_orderbook.py`` exists. Must fail (ImportError / feature
absent) on first run, then pass after GREEN.

The collector drives ``BitgetPublicClient.get_order_book`` (read-only public depth) over a
set of symbols, gathering N snapshots each, and aggregates them through the fail-closed
``summarize_spreads`` gate. It is exercised here with a fake client (no network, no secrets)
to prove the gather/aggregate wiring; the real CLI path is the same code with the default
client.
"""
import asyncio
import time

import pytest

from src.market.orderbook import OrderBook


def _book(symbol, now_ms):
    return OrderBook(symbol=symbol, bids=((99.95, 1.0),), asks=((100.05, 1.0),), ts_ms=now_ms)


class _FakeClient:
    def __init__(self, per_symbol):
        self._per_symbol = per_symbol
        self.calls = []

    async def get_order_book(self, symbol, limit=20):
        self.calls.append(symbol)
        seq = self._per_symbol[symbol]
        return seq[len(self.calls) % len(seq)]


def test_run_calibration_aggregates_snapshots_via_fake_client():
    from scripts.observe_orderbook import run_calibration

    now = int(time.time() * 1000)
    client = _FakeClient({"BTCUSDT": [_book("BTCUSDT", now), _book("BTCUSDT", now)]})
    res = asyncio.run(run_calibration(["BTCUSDT"], snapshots_per_symbol=2, client=client))
    assert "BTCUSDT" in res
    assert res["BTCUSDT"]["n_valid"] == 2
    assert res["BTCUSDT"]["rejected"] == 0
    assert res["BTCUSDT"]["spread_bps_median"] == pytest.approx(10.0)


def test_run_calibration_skips_symbol_on_error_fail_closed():
    from scripts.observe_orderbook import run_calibration

    now = int(time.time() * 1000)

    class _ErrClient:
        async def get_order_book(self, symbol, limit=20):
            raise __import__("src.market.bitget_public", fromlist=["PublicMarketError"]).PublicMarketError("ORDERBOOK_SCHEMA")

    res = asyncio.run(run_calibration(["BTCUSDT"], snapshots_per_symbol=2, client=_ErrClient()))
    # fail-closed: a symbol that errors on every snapshot yields no valid data and is not
    # presented as a cheap market.
    assert "BTCUSDT" not in res
