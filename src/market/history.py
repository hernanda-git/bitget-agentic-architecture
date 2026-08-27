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
import math
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
    """Paginate the public funding history backward from `end_time_ms`, deduping overlaps.
    Some venue responses cap the page size well below `limit`, so a single request
    can under-cover long candle windows. Loop backward until `limit` unique
    settlements are collected or history is exhausted.
    """
    if limit < 1:
        raise ValueError("funding limit must be >= 1")
    collected: dict[int, FundingRecord] = {}
    cursor = end_time_ms
    while len(collected) < limit:
        page = await client.fetch_history_funding_rate(symbol, limit=min(limit - len(collected), 1000),
                                                       end_time_ms=cursor)
        if not page:
            break
        added = 0
        for funding_time_ms, rate in page:
            if funding_time_ms not in collected:
                collected[funding_time_ms] = FundingRecord(funding_time_ms, rate)
                added += 1
        earliest = min(ts for ts, _ in page)
        cursor = earliest - 1
        if added == 0 or cursor <= 0:
            break
    return tuple(sorted(collected.values(), key=lambda r: r.funding_time_ms))


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


_GRANULARITY_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
_FUNDING_INTERVAL_MS = 8 * 3_600_000


def expected_interval_ms(granularity: str) -> int:
    """Map a candle granularity like ``1m``/``5m``/``1h``/``1d`` to milliseconds."""
    if len(granularity) >= 2 and granularity[-1] in _GRANULARITY_UNIT_MS and granularity[:-1].isdigit():
        return int(granularity[:-1]) * _GRANULARITY_UNIT_MS[granularity[-1]]
    raise ValueError(f"unsupported granularity: {granularity!r}")


@dataclass(frozen=True)
class DataQualityReport:
    """Structural data-quality facts about a :class:`HistoryDataset`.

    ``ok`` is structural soundness (chronology + price integrity). Gaps,
    zero-volume bars, funding coverage, staleness, single-bar outliers, and
    funding anomalies are reported as measured facts, never silently dropped.
    """

    symbol: str
    granularity: str
    candle_count: int
    duplicate_timestamps: int
    non_chronological: int
    bad_prices: int
    gaps: tuple[dict, ...]
    max_missing_bars: int
    zero_volume_bars: int
    funding_expected_settlements: int
    funding_records_in_range: int
    funding_missing: int
    data_age_ms: int
    max_data_age_ms: int | None
    max_single_bar_return_bps: float
    funding_anomalies: int

    @property
    def price_integrity_ok(self) -> bool:
        return self.bad_prices == 0

    @property
    def freshness_ok(self) -> bool:
        return self.max_data_age_ms is None or self.data_age_ms <= self.max_data_age_ms

    @property
    def ok(self) -> bool:
        return (self.duplicate_timestamps == 0 and self.non_chronological == 0
                and self.bad_prices == 0)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol, "granularity": self.granularity, "ok": self.ok,
            "candle_count": self.candle_count, "duplicate_timestamps": self.duplicate_timestamps,
            "non_chronological": self.non_chronological, "bad_prices": self.bad_prices,
            "price_integrity_ok": self.price_integrity_ok, "gaps": list(self.gaps),
            "max_missing_bars": self.max_missing_bars, "zero_volume_bars": self.zero_volume_bars,
            "funding_expected_settlements": self.funding_expected_settlements,
            "funding_records_in_range": self.funding_records_in_range,
            "funding_missing": self.funding_missing, "data_age_ms": self.data_age_ms,
            "max_data_age_ms": self.max_data_age_ms, "freshness_ok": self.freshness_ok,
            "max_single_bar_return_bps": self.max_single_bar_return_bps,
            "funding_anomalies": self.funding_anomalies,
        }


def data_quality_report(dataset: HistoryDataset, *, max_data_age_ms: int | None = None,
                        max_funding_rate: float = 0.05) -> DataQualityReport:
    """Measure structural quality of a stored dataset without mutating it.

    ``max_data_age_ms`` enables a freshness gate: if set, ``freshness_ok`` is
    False when the newest candle is older than the fetch time by more than that
    span. ``max_funding_rate`` flags funding settlements whose magnitude is
    implausible for the venue (non-finite or beyond the bound).
    """
    import math
    candles = dataset.candles
    if not candles:
        raise ValueError("cannot assess data quality of an empty dataset")
    step = expected_interval_ms(dataset.granularity)

    seen: set[int] = set()
    duplicates = 0
    for ts in (c.source_ts_ms for c in candles):
        if ts in seen:
            duplicates += 1
        seen.add(ts)

    non_chronological = sum(
        1 for a, b in zip(candles, candles[1:]) if b.source_ts_ms < a.source_ts_ms
    )

    # Price integrity: NaN/inf survive Candle.__post_init__ because every
    # comparison with them is False, so they must be caught explicitly here.
    bad_prices = 0
    prev_close: float | None = None
    max_bar_return_bps = 0.0
    for candle in candles:
        if not all(math.isfinite(v) for v in
                   (candle.open, candle.high, candle.low, candle.close, candle.volume)):
            bad_prices += 1
        if prev_close is not None and prev_close > 0:
            move_bps = abs(candle.close - prev_close) / prev_close * 10_000
            if move_bps > max_bar_return_bps:
                max_bar_return_bps = move_bps
        prev_close = candle.close

    gaps: list[dict] = []
    max_missing = 0
    for a, b in zip(candles, candles[1:]):
        delta = b.source_ts_ms - a.source_ts_ms
        if delta > step:
            missing = round(delta / step) - 1
            gaps.append({"start_ms": a.source_ts_ms, "end_ms": b.source_ts_ms,
                         "gap_ms": delta, "missing_bars": missing})
            max_missing = max(max_missing, missing)

    zero_volume = sum(1 for c in candles if c.volume == 0.0)

    first_ts = min(c.source_ts_ms for c in candles)
    last_ts = max(c.source_ts_ms for c in candles)
    data_age_ms = dataset.fetched_at_ms - last_ts
    expected_settlements = int((last_ts - first_ts) // _FUNDING_INTERVAL_MS)
    in_range = sum(1 for f in dataset.funding if first_ts < f.funding_time_ms <= last_ts)
    funding_missing = max(0, expected_settlements - in_range)
    funding_anomalies = sum(
        1 for f in dataset.funding
        if (not math.isfinite(f.funding_rate)) or abs(f.funding_rate) > max_funding_rate
    )

    return DataQualityReport(
        symbol=dataset.symbol, granularity=dataset.granularity, candle_count=len(candles),
        duplicate_timestamps=duplicates, non_chronological=non_chronological,
        bad_prices=bad_prices, gaps=tuple(gaps), max_missing_bars=max_missing,
        zero_volume_bars=zero_volume, funding_expected_settlements=expected_settlements,
        funding_records_in_range=in_range, funding_missing=funding_missing,
        data_age_ms=data_age_ms, max_data_age_ms=max_data_age_ms,
        max_single_bar_return_bps=max_bar_return_bps, funding_anomalies=funding_anomalies,
    )


def coverage_gate(report: DataQualityReport, *, max_missing_fraction: float = 0.25,
                  max_single_gap_bars: int | None = None) -> bool:
    """Fail-closed coverage gate: reject datasets with too many missing bars.

    Walk-forward time indices assume a near-continuous candle series. A dataset
    with large holes (missing bars between consecutive candles) distorts those
    indices and quietly biases the replay. The structural ``ok`` gate ignores
    gaps, so this gate exists to fail closed on sparse series.

    Returns ``False`` (reject) when the missing-bar fraction exceeds
    ``max_missing_fraction`` (relative sparseness) OR a single gap is larger than
    ``max_single_gap_bars`` (absolute hole size, when provided). Returns ``True``
    only when neither condition is violated. A missing fraction means the series
    would be distorted; fail closed, never silently proceed.

    ``max_missing_fraction`` is the fraction of *expected* total bars that are
    absent; ``max_single_gap_bars`` caps the largest single hole in bars.
    """
    if not isinstance(max_missing_fraction, (int, float)) or not math.isfinite(max_missing_fraction) \
            or not 0.0 <= max_missing_fraction <= 1.0:
        raise ValueError("max_missing_fraction must be a finite number in [0, 1]")
    if max_single_gap_bars is not None and (not isinstance(max_single_gap_bars, int)
                                            or max_single_gap_bars < 0):
        raise ValueError("max_single_gap_bars must be a non-negative integer")

    total_missing = sum(int(g["missing_bars"]) for g in report.gaps)
    expected = report.candle_count + total_missing
    if expected <= 0:
        return True  # nothing to measure; the structural gate handles emptiness
    if total_missing / expected > max_missing_fraction:
        return False
    if max_single_gap_bars is not None and report.max_missing_bars > max_single_gap_bars:
        return False
    return True


@dataclass(frozen=True)
class FundingReadiness:
    """Whether a dataset may be evaluated with real (observed) funding.

    ``ok`` is False when the dataset spans funding settlements but carries no
    in-range funding records (real funding would be silently unmodeled) or when
    the missing fraction of expected settlements is too high. This is a
    fail-closed gate: absence of coverage is treated as "do not model funding",
    never as "funding is free".
    """

    ok: bool
    reason: str
    funding_records_in_range: int
    expected_settlements: int
    funding_missing: int

    def as_dict(self) -> dict:
        return {
            "ok": self.ok, "reason": self.reason,
            "funding_records_in_range": self.funding_records_in_range,
            "expected_settlements": self.expected_settlements,
            "funding_missing": self.funding_missing,
        }


def real_funding_readiness(dataset: HistoryDataset, report: DataQualityReport, *,
                           min_funding_records_in_range: int = 1,
                           max_funding_missing_fraction: float = 0.5) -> FundingReadiness:
    """Decide whether ``real_funding=True`` is defensible for this dataset.

    ``report`` is the :class:`DataQualityReport` already produced for the same
    dataset (it carries the funding-coverage counts). The gate fails closed
    when there are no in-range funding records despite the window spanning
    funding settlements, or when too many expected settlements are missing.
    """
    if min_funding_records_in_range < 0:
        raise ValueError("min_funding_records_in_range must be >= 0")
    if not 0.0 <= max_funding_missing_fraction <= 1.0:
        raise ValueError("max_funding_missing_fraction must be in [0, 1]")
    in_range = report.funding_records_in_range
    expected = report.funding_expected_settlements
    missing = report.funding_missing
    if expected >= 1 and in_range < min_funding_records_in_range:
        return FundingReadiness(False, "no in-range funding records for a window that spans settlements",
                                in_range, expected, missing)
    if expected >= 1 and missing / expected > max_funding_missing_fraction:
        return FundingReadiness(False, "funding coverage too sparse for real-funding modeling",
                                in_range, expected, missing)
    return FundingReadiness(True, "", in_range, expected, missing)


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
