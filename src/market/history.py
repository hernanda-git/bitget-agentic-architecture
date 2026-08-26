"""Acquire and store real public historical market data (no signing, no credentials).

This module turns the unauthenticated :class:`BitgetPublicClient` into a durable,
integrity-checked historical dataset that the deterministic evaluation engine can
replay instead of the synthetic fixture. Historical bid/ask is not retrievable from
the public API, so spread is represented by an explicit assumed half-spread in
basis points and is reported as an assumption, never presented as observed data.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Iterable

from src.market.bitget_public import BitgetPublicClient, PublicMarketError
from src.market.models import Candle, MarketSnapshot


@dataclass(frozen=True)
class FundingRecord:
    funding_time_ms: int
    funding_rate: float


@dataclass(frozen=True)
class HistoryDataset:
    symbol: str
    product_type: str
    granularity: str
    fetched_at_ms: int
    candles: tuple[Candle, ...]
    funding: tuple[FundingRecord, ...]
    assumed_half_spread_bps: float
    source: str = "bitget-public"

    def integrity_hash(self) -> str:
        payload = {
            "symbol": self.symbol,
            "product_type": self.product_type,
            "granularity": self.granularity,
            "fetched_at_ms": self.fetched_at_ms,
            "candles": [c.__dict__ for c in self.candles],
            "funding": [f.__dict__ for f in self.funding],
            "assumed_half_spread_bps": self.assumed_half_spread_bps,
            "source": self.source,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "product_type": self.product_type,
            "granularity": self.granularity,
            "fetched_at_ms": self.fetched_at_ms,
            "assumed_half_spread_bps": self.assumed_half_spread_bps,
            "source": self.source,
            "integrity_hash": self.integrity_hash(),
            "candles": [list(c.__dict__.values()) for c in self.candles],
            "funding": [list(f.__dict__.values()) for f in self.funding],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryDataset":
        candles = tuple(Candle(*row) for row in data["candles"])
        funding = tuple(FundingRecord(*row) for row in data.get("funding", []))
        dataset = cls(
            symbol=data["symbol"], product_type=data["product_type"], granularity=data["granularity"],
            fetched_at_ms=data["fetched_at_ms"], candles=candles, funding=funding,
            assumed_half_spread_bps=data["assumed_half_spread_bps"], source=data.get("source", "bitget-public"),
        )
        if data.get("integrity_hash") != dataset.integrity_hash():
            raise ValueError("history dataset integrity hash mismatch")
        return dataset


async def fetch_candle_history(client: BitgetPublicClient, symbol: str, granularity: str = "1m",
                               *, end_time_ms: int, max_candles: int, page_size: int = 1000) -> tuple[Candle, ...]:
    """Paginate the public candle API backward from `end_time_ms`, deduping overlaps."""
    if max_candles < 1:
        raise ValueError("max_candles must be >= 1")
    if end_time_ms <= 0:
        raise ValueError("end_time_ms must be positive")
    page_size = min(max(int(page_size), 1), 1000)
    collected: dict[int, Candle] = {}
    cursor = end_time_ms
    while len(collected) < max_candles:
        need = min(page_size, max_candles - len(collected))
        page = await client.fetch_candles(symbol, granularity, need, end_time_ms=cursor, allow_partial=True)
        if not page:
            break
        added = 0
        for candle in page:
            if candle.source_ts_ms not in collected:
                collected[candle.source_ts_ms] = candle
                added += 1
        earliest = min(c.source_ts_ms for c in page)
        cursor = earliest - 1
        if added == 0 or cursor <= 0:
            break
    return tuple(sorted(collected.values(), key=lambda c: c.source_ts_ms))


async def fetch_funding_history(client: BitgetPublicClient, symbol: str, *, limit: int = 100,
                                end_time_ms: int | None = None) -> tuple[FundingRecord, ...]:
    records = await client.fetch_history_funding_rate(symbol, limit=limit, end_time_ms=end_time_ms)
    return tuple(FundingRecord(ft, rate) for ft, rate in records)


async def acquire_dataset(client: BitgetPublicClient, symbol: str, granularity: str = "1m",
                          *, end_time_ms: int | None = None, max_candles: int = 1500,
                          funding_limit: int = 200, assumed_half_spread_bps: float = 0.5,
                          fetched_at_ms: int | None = None) -> HistoryDataset:
    """Acquire candles (and funding history) for one symbol as a durable dataset."""
    end_time_ms = end_time_ms or int(time.time() * 1000)
    candles = await fetch_candle_history(client, symbol, granularity, end_time_ms=end_time_ms, max_candles=max_candles)
    funding = await fetch_funding_history(client, symbol, limit=funding_limit, end_time_ms=end_time_ms)
    return HistoryDataset(
        symbol=symbol, product_type=client.product_type, granularity=granularity,
        fetched_at_ms=fetched_at_ms or int(time.time() * 1000), candles=candles, funding=funding,
        assumed_half_spread_bps=assumed_half_spread_bps,
    )


def _nearest_funding_rate(funding: tuple[FundingRecord, ...], observed_ms: int) -> float | None:
    chosen: FundingRecord | None = None
    for record in funding:
        if record.funding_time_ms <= observed_ms:
            if chosen is None or record.funding_time_ms > chosen.funding_time_ms:
                chosen = record
    return chosen.funding_rate if chosen is not None else None


def snapshots_from_dataset(dataset: HistoryDataset, window: int = 30,
                           candle_window: str = "1m") -> tuple[MarketSnapshot, ...]:
    """Build evaluation snapshots from a historical dataset.

    The mark price is the candle close; bid/ask are derived from the documented
    assumed half-spread. Funding rate is attached from the nearest prior funding
    record when available. Each snapshot carries the trailing candle window so
    indicators have context, mirroring the synthetic evaluation fixture.
    """
    if not dataset.candles:
        raise ValueError("cannot build snapshots from an empty dataset")
    if window < 1:
        raise ValueError("window must be >= 1")
    half = max(dataset.assumed_half_spread_bps, 0.0) / 10_000
    funding_sorted = sorted(dataset.funding, key=lambda f: f.funding_time_ms)
    fi = 0
    out: list[MarketSnapshot] = []
    for index, candle in enumerate(dataset.candles):
        start = max(0, index - window + 1)
        window_candles = dataset.candles[start:index + 1]
        mark = candle.close
        bid = mark * (1 - half)
        ask = mark * (1 + half)
        observed = candle.source_ts_ms  # decide at bar close; candle ts <= observed
        # Funding is charged only on the bar at/after an actual funding settlement,
        # using the real settlement rate. Charging on every bar would overstate
        # funding by the number of bars between settlements (~480x for 1m vs 8h).
        funding_rate: float | None = None
        while fi < len(funding_sorted) and funding_sorted[fi].funding_time_ms <= observed:
            funding_rate = funding_sorted[fi].funding_rate
            fi += 1
        snapshot = MarketSnapshot(
            symbol=dataset.symbol, mark_price=mark, bid=bid, ask=ask, funding_rate=funding_rate,
            open_interest=None, volume=candle.volume, observed_ts_ms=observed, source_ts_ms=candle.source_ts_ms,
            candles=window_candles, candles_by_window={candle_window: window_candles},
            required_windows=(candle_window,), feature_version="market-v1",
        ).with_hash()
        out.append(snapshot)
    return tuple(out)


async def main_acquire(symbol: str, granularity: str, max_candles: int, output_path: str,
                       assumed_half_spread_bps: float = 0.5, end_time_ms: int | None = None,
                       product_type: str = "SUSDT-FUTURES") -> HistoryDataset:
    client = BitgetPublicClient(venue="bitget", product_type=product_type)
    dataset = await acquire_dataset(client, symbol, granularity, end_time_ms=end_time_ms,
                                    max_candles=max_candles, assumed_half_spread_bps=assumed_half_spread_bps)
    from pathlib import Path
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(dataset.to_dict(), indent=2, sort_keys=True) + "\n")
    return dataset


def load_dataset(path):
    from pathlib import Path
    if isinstance(path, (str, Path)):
        data = json.loads(Path(path).read_text())
    else:
        data = json.loads(path.read_text())
    return HistoryDataset.from_dict(data)
