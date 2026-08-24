"""Freshness and consistency checks for market snapshots."""
from __future__ import annotations

from dataclasses import dataclass

from src.market.models import MarketSnapshot


@dataclass(frozen=True)
class FreshnessResult:
    ok: bool
    reason: str


def check_freshness(snapshot: MarketSnapshot, now_ts_ms: int, max_age_seconds: float,
                    max_clock_skew_seconds: float = 30.0) -> FreshnessResult:
    if now_ts_ms < snapshot.observed_ts_ms:
        return FreshnessResult(False, "LOCAL_CLOCK_BEFORE_OBSERVATION")
    age_s = (now_ts_ms - snapshot.observed_ts_ms) / 1000
    if age_s > max_age_seconds:
        return FreshnessResult(False, "STALE_MARKET_DATA")
    skew_s = abs(snapshot.observed_ts_ms - snapshot.source_ts_ms) / 1000
    if skew_s > max_clock_skew_seconds:
        return FreshnessResult(False, "SOURCE_CLOCK_SKEW")
    if not snapshot.snapshot_hash or snapshot.snapshot_hash != snapshot.computed_hash():
        return FreshnessResult(False, "SNAPSHOT_HASH_INVALID")
    return FreshnessResult(True, "FRESH")
