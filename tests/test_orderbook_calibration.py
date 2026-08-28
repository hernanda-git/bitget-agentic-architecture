"""TDD for observed order-book spread/depth calibration (real-venue cost surface).

Written BEFORE ``src/market/orderbook_calibration.py`` exists. Must fail (ImportError /
feature absent) on first run, then pass after GREEN.

The calibration aggregates raw snapshots of observed top-of-book spread and depth within
price bands per symbol, FAIL-CLOSED: any snapshot rejected by the order-book quality gate
is excluded from the statistics rather than poisoning the cost estimate. This is pure
measurement: nothing here changes the deterministic promotion gate, places orders, or
computes realized PnL.
"""
import statistics

from src.market.orderbook import OrderBook, parse_order_book
from src.market.orderbook_quality import check_order_book


def _ob(symbol, best_bid, best_ask, ts_ms, *, bid_levels=((1.0,),), ask_levels=((1.0,),)):
    bids = ((best_bid, 1.0),) + tuple((best_bid - (i + 1) * 0.05, 1.0) for i in range(len(bid_levels) - 1))
    asks = ((best_ask, 1.0),) + tuple((best_ask + (i + 1) * 0.05, 1.0) for i in range(len(ask_levels) - 1))
    return OrderBook(symbol=symbol, bids=bids, asks=asks, ts_ms=ts_ms)


def test_summarize_spreads_aggregates_per_symbol():
    from src.market.orderbook_calibration import summarize_spreads

    # Two valid snapshots for BTC, one for ETH. BTC mid 100 spread 10bps; ETH mid 2000 spread 5bps.
    obs = [
        _ob("BTCUSDT", 99.95, 100.05, 1_000_000),
        _ob("BTCUSDT", 99.95, 100.05, 1_000_100),
        _ob("ETHUSDT", 1999.5, 2000.5, 1_000_000),
    ]
    out = summarize_spreads(obs, now_ms=1_000_200, max_age_ms=60_000)
    assert set(out) == {"BTCUSDT", "ETHUSDT"}
    assert out["BTCUSDT"]["n_valid"] == 2
    assert out["BTCUSDT"]["spread_bps_median"] == pytest.approx(10.0)
    assert out["ETHUSDT"]["spread_bps_median"] == pytest.approx(5.0)
    # depth within 5bps: only the top level (size 1.0) on each side => total 2.0 per snapshot
    assert out["BTCUSDT"]["depth_5bps_mean"] == pytest.approx(2.0)
    assert out["BTCUSDT"]["mid_mean"] == pytest.approx(100.0)


def test_summarize_spreads_excludes_rejected_snapshots():
    from src.market.orderbook_calibration import summarize_spreads

    good = _ob("BTCUSDT", 99.95, 100.05, 1_000_000)
    # future-dated snapshot -> rejected by the gate (fail-closed, excluded)
    future = _ob("BTCUSDT", 99.95, 100.05, 5_000_000_000_000)
    out = summarize_spreads([good, future], now_ms=1_000_100, max_age_ms=10_000)
    assert out["BTCUSDT"]["n"] == 2
    assert out["BTCUSDT"]["n_valid"] == 1
    assert out["BTCUSDT"]["rejected"] == 1
    assert out["BTCUSDT"]["spread_bps_median"] == pytest.approx(10.0)


def test_summarize_spreads_all_rejected_reports_no_spread():
    from src.market.orderbook_calibration import summarize_spreads

    future = _ob("BTCUSDT", 99.95, 100.05, 5_000_000_000_000)
    out = summarize_spreads([future], now_ms=1_000_100, max_age_ms=10_000)
    assert out["BTCUSDT"]["n_valid"] == 0
    assert out["BTCUSDT"]["rejected"] == 1
    assert out["BTCUSDT"]["spread_bps_median"] is None


import pytest  # noqa: E402  (imported last so the module-level helper above is defined first)
