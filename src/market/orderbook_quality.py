"""Fail-closed quality gate for observed order books.

Mirrors the candle/freshness gates: a book that is empty, crossed, stale, or carrying a
future timestamp is refused rather than yielding a silently wrong spread. The gate is
pure and does not perform I/O, so it is trivially testable and safe to call on every
snapshot before any spread/depth figure enters an evaluation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from src.market.orderbook import OrderBook, OrderBookError, mid_price, top_spread_bps


@dataclass(frozen=True)
class OrderBookQuality:
    ok: bool
    reasons: tuple[str, ...]
    spread_bps: float
    mid: float
    best_bid: float
    best_ask: float
    age_ms: int


def check_order_book(ob: OrderBook, *, now_ms: int | None = None, max_age_ms: int = 60_000,
                     min_bid_levels: int = 1, min_ask_levels: int = 1) -> OrderBookQuality:
    """Validate an order book. Any defect sets ``ok=False`` with an explicit reason.

    Fail-closed: a crossed book, empty side, non-positive size, future timestamp, or a
    book older than ``max_age_ms`` is rejected. Spread/mid are only reported when both
    sides are present and uncrossed.
    """
    reasons: list[str] = []
    if len(ob.bids) < min_bid_levels:
        reasons.append("EMPTY_BIDS")
    if len(ob.asks) < min_ask_levels:
        reasons.append("EMPTY_ASKS")
    if ob.bids and ob.asks and ob.bids[0][0] >= ob.asks[0][0]:
        reasons.append("CROSSED_BOOK")
    if any(sz <= 0 for _, sz in ob.bids) or any(sz <= 0 for _, sz in ob.asks):
        reasons.append("NONPOSITIVE_SIZE")

    now = now_ms if now_ms is not None else int(time.time() * 1000)
    age = now - ob.ts_ms
    if age < 0:
        reasons.append("FUTURE_TS")
    elif age > max_age_ms:
        reasons.append("STALE_BOOK")

    ok = not reasons
    if ob.bids and ob.asks and ob.bids[0][0] < ob.asks[0][0]:
        try:
            spread = top_spread_bps(ob)
            mid = mid_price(ob)
        except OrderBookError:
            spread, mid = float("nan"), 0.0
    else:
        spread, mid = float("nan"), 0.0

    return OrderBookQuality(
        ok=ok,
        reasons=tuple(reasons),
        spread_bps=spread,
        mid=mid,
        best_bid=ob.bids[0][0] if ob.bids else 0.0,
        best_ask=ob.asks[0][0] if ob.asks else 0.0,
        age_ms=max(0, age),
    )
