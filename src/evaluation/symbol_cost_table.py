"""Symbol-specific observed-spread cost table (measurement only, fail-closed).

Phase 36 measured a real-venue per-symbol top-of-book spread and showed a single
global assumed half-spread is simultaneously too conservative on majors
(BTC/ETH/SOL ~0.01-0.1 bps) and too optimistic on alts (ADA ~4.8 bps,
AVAX/SUI/NEAR ~1.3-1.6 bps). This module turns that measurement into a loadable,
fail-closed cost table and a per-symbol bid/ask recalibration so the deterministic
baseline replays with the OBSERVED spread instead of the single global assumed
half-spread that ``snapshots_from_dataset`` synthesizes for every symbol.

It never chooses quantity, leverage, protection, or changes the deterministic
promotion gate, and it never computes realized PnL. The table is a cost SURFACE.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

from src.market.models import MarketSnapshot, replace

# Liquidity-tier thresholds on the observed full top-of-book spread, in bps.
# TIER_TIGHT  : observed spread < 0.1 bps  (deepest books: BTC/ETH/SOL)
# TIER_MODERATE: 0.1 <= observed spread < 1.0 bps (XRP-class)
# TIER_WIDE   : observed spread >= 1.0 bps (alts with thinner books)
TIER_TIGHT_MAX_BPS = 0.1
TIER_MODERATE_MAX_BPS = 1.0


class LiquidityTier(str, Enum):
    TIER_TIGHT = "TIER_TIGHT"
    TIER_MODERATE = "TIER_MODERATE"
    TIER_WIDE = "TIER_WIDE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ObservedCostTable:
    """Observed per-symbol execution-spread surface.

    ``spreads_bps`` maps a symbol to its observed full top-of-book spread in bps.
    A symbol is present ONLY when a positive-finite observed spread exists; there
    is deliberately no cheap fallback, so a caller that forgets to supply a symbol
    fails closed instead of silently pricing it as free.
    """

    spreads_bps: Mapping[str, float]
    source: str
    depths: Mapping[str, dict] = field(default_factory=dict)

    def spread_for(self, symbol: str) -> float:
        """Observed spread in bps, or raise (fail-closed) when unknown."""
        if symbol not in self.spreads_bps:
            raise KeyError(f"no observed spread for {symbol!r} in cost table")
        s = self.spreads_bps[symbol]
        if not (isinstance(s, (int, float)) and math.isfinite(s) and s > 0):
            raise ValueError(f"observed spread for {symbol!r} is not positive-finite: {s!r}")
        return float(s)


def load_observed_spread_table(path: str | Path) -> ObservedCostTable:
    """Load an observed-spread table from a Phase 36 calibration JSON.

    Fail-closed: a missing file raises ``FileNotFoundError``; a file without a
    ``calibration`` object raises ``ValueError``; and any symbol whose observed
    median spread is missing / non-finite / non-positive is OMITTED (never
    presented as a cheap market). Only symbols with a usable observed spread
    enter the table.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    data = json.loads(p.read_text())
    calibration = data.get("calibration")
    if not isinstance(calibration, dict):
        raise ValueError(f"{p}: calibration object missing or not an object")
    spreads: dict[str, float] = {}
    depths: dict[str, dict] = {}
    for symbol, entry in calibration.items():
        if not isinstance(entry, dict):
            continue
        median = entry.get("spread_bps_median")
        n_valid = entry.get("n_valid", 0)
        if not (isinstance(median, (int, float)) and math.isfinite(median)
                and median > 0 and isinstance(n_valid, int) and n_valid > 0):
            # no usable observed spread -> omit (fail closed, never cheap)
            continue
        spreads[symbol] = float(median)
        if "depth_5bps_mean" in entry or "depth_60bps_mean" in entry:
            depths[symbol] = {
                "depth_5bps_mean": entry.get("depth_5bps_mean"),
                "depth_60bps_mean": entry.get("depth_60bps_mean"),
                "mid_mean": entry.get("mid_mean"),
            }
    if not spreads:
        raise ValueError(f"{p}: no symbols with a usable observed spread")
    return ObservedCostTable(spreads_bps=spreads, source=str(p), depths=depths)


def liquidity_tier(spread_bps: float) -> LiquidityTier:
    """Classify an observed spread into a liquidity tier (fail-closed on bad input)."""
    if not (isinstance(spread_bps, (int, float)) and math.isfinite(spread_bps) and spread_bps > 0):
        raise ValueError(f"spread_bps must be positive-finite, got {spread_bps!r}")
    if spread_bps < TIER_TIGHT_MAX_BPS:
        return LiquidityTier.TIER_TIGHT
    if spread_bps < TIER_MODERATE_MAX_BPS:
        return LiquidityTier.TIER_MODERATE
    return LiquidityTier.TIER_WIDE


def classify_symbols(table: ObservedCostTable, symbols: Iterable[str]) -> dict[LiquidityTier, list[str]]:
    """Group symbols by observed-spread tier; symbols absent from the table land
    in ``UNKNOWN`` (never folded into a real tier)."""
    out: dict[LiquidityTier, list[str]] = defaultdict(list)
    for sym in symbols:
        if sym in table.spreads_bps:
            out[liquidity_tier(table.spread_for(sym))].append(sym)
        else:
            out[LiquidityTier.UNKNOWN].append(sym)
    return dict(out)


def tier_median_spread(table: ObservedCostTable, symbols: Iterable[str]) -> float:
    """Median observed spread across the given symbols (fail-closed if none known)."""
    vals = [table.spread_for(s) for s in symbols if s in table.spreads_bps]
    if not vals:
        raise ValueError("no observed spread available for any of the given symbols")
    return statistics.median(vals)


def recalibrate_spread(snapshot: MarketSnapshot, spread_bps: float) -> MarketSnapshot:
    """Return a snapshot whose bid/ask carry the observed ``spread_bps``.

    The historical corpus synthesizes bid/ask from ONE global assumed half-spread,
    so every symbol currently replays with the same ~1.0 bps spread. Re-deriving
    bid/ask from the observed per-symbol spread makes the realized spread cost
    (``abs(quoted - mark)`` in ``FakeExchange``) and the cost gate
    (``snapshot.spread_bps`` via ``cost_fraction``) reflect the real venue, not
    the global assumption. The mark price is preserved.
    """
    if not (isinstance(spread_bps, (int, float)) and math.isfinite(spread_bps) and spread_bps > 0):
        raise ValueError(f"spread_bps must be positive-finite, got {spread_bps!r}")
    half = spread_bps / 2.0 / 10_000.0
    mark = snapshot.mark_price
    bid = mark * (1.0 - half)
    ask = mark * (1.0 + half)
    return replace(snapshot, bid=bid, ask=ask, snapshot_hash="").with_hash()


def recalibrate_snapshots_by_symbol(snapshots: Iterable[MarketSnapshot],
                                    table: ObservedCostTable) -> tuple[MarketSnapshot, ...]:
    """Recalibrate every snapshot to its symbol's observed spread (fail-closed).

    Any symbol missing from the table raises ``KeyError`` so a caller cannot
    accidentally price an uncalibrated symbol with the global assumption.
    """
    out: list[MarketSnapshot] = []
    for s in snapshots:
        sp = table.spread_for(s.symbol)
        out.append(recalibrate_spread(s, sp))
    return tuple(out)
