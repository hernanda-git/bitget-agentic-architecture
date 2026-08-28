"""Observed order-book cost surface (read-only public depth).

The historical cost model previously used an *assumed* half-spread because the selected
public candle endpoint does not expose historical bid/ask. This module adds the live,
observed top-of-book spread and depth so walk-forward / cost-stress conclusions can be
calibrated against the real venue. It is measurement only: nothing here chooses quantity,
leverage, protection, or changes the deterministic promotion gate.

All parsing is fail-closed: a crossed, empty, or malformed book raises ``OrderBookError``
rather than yielding a silently wrong spread.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

Level = Tuple[float, float]  # (price, size)


class OrderBookError(ValueError):
    """Raised when a raw order-book payload cannot be normalized safely."""


@dataclass(frozen=True)
class OrderBook:
    symbol: str
    bids: Tuple[Level, ...]  # strictly descending price (best bid first)
    asks: Tuple[Level, ...]  # strictly ascending price (best ask first)
    ts_ms: int
    source: str = "bitget"

    def __post_init__(self) -> None:
        # ``OrderBook`` is a permissive container: structural validity (empty/crossed/
        # stale) is judged by ``check_order_book`` so the gate is the single fail-closed
        # authority. Construction only rejects values that could not possibly be a book.
        if not self.symbol or not self.symbol.isupper():
            raise OrderBookError("invalid symbol")
        for px, sz in self.bids + self.asks:
            if px <= 0 or sz <= 0:
                raise OrderBookError("nonpositive price or size")
        if self.ts_ms <= 0:
            raise OrderBookError("invalid timestamp")


def parse_order_book(symbol: str, payload: dict, *, ts_ms: int | None = None,
                     source: str = "bitget") -> OrderBook:
    """Normalize a raw Bitget v2 orderbook payload into an ``OrderBook``.

    The raw payload is ``{"bids": [[price, size], ...], "asks": [...], "ts": <ms>}``.
    Bids are sorted descending by price and asks ascending so the first element of each
    is the best level. Raises ``OrderBookError`` on any malformed, empty, or crossed book.
    """
    if not isinstance(payload, dict):
        raise OrderBookError("payload must be a dict")
    bids_raw = payload.get("bids") or []
    asks_raw = payload.get("asks") or []
    try:
        bids = tuple((float(p), float(s)) for p, s in bids_raw)
        asks = tuple((float(p), float(s)) for p, s in asks_raw)
    except (TypeError, ValueError) as exc:
        raise OrderBookError("non-numeric level") from exc
    if not bids or not asks:
        raise OrderBookError("empty book")
    bids = tuple(sorted(bids, key=lambda lv: lv[0], reverse=True))
    asks = tuple(sorted(asks, key=lambda lv: lv[0]))
    if bids[0][0] >= asks[0][0]:
        raise OrderBookError("crossed book")
    resolved_ts = ts_ms if ts_ms is not None else int(payload.get("ts", 0) or 0)
    return OrderBook(symbol=symbol, bids=bids, asks=asks, ts_ms=resolved_ts, source=source)


def mid_price(ob: OrderBook) -> float:
    """Mid of the best bid/ask."""
    return (ob.bids[0][0] + ob.asks[0][0]) / 2.0


def top_spread_bps(ob: OrderBook) -> float:
    """Top-of-book spread in basis points of mid."""
    mid = mid_price(ob)
    if mid <= 0:
        raise OrderBookError("nonpositive mid")
    return (ob.asks[0][0] - ob.bids[0][0]) / mid * 10_000.0


def depth_within_bps(ob: OrderBook, price_bps: float) -> dict:
    """Liquidity available on each side within ``+/-price_bps`` of mid.

    Returns the summed contract size that can be consumed without crossing the band
    (bids with price >= mid - band; asks with price <= mid + band). This is the
    depth a position of that notional could take before the executable price moves
    beyond the band, characterizing real execution capacity beyond the top spread.
    """
    if price_bps < 0:
        raise OrderBookError("price_bps must be non-negative")
    mid = mid_price(ob)
    band = (price_bps / 10_000.0) * mid
    lo, hi = mid - band, mid + band
    bid_depth = sum(sz for px, sz in ob.bids if lo <= px <= mid + 1e-12)
    ask_depth = sum(sz for px, sz in ob.asks if mid - 1e-12 <= px <= hi)
    return {
        "mid": mid,
        "band_bps": price_bps,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "total_depth": bid_depth + ask_depth,
    }
