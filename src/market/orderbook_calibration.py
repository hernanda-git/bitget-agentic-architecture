"""Observed order-book spread/depth calibration (real-venue cost surface).

Aggregates raw snapshots of observed top-of-book spread and depth within price bands per
symbol. Pure and fail-closed: every snapshot is judged by ``check_order_book`` and any
rejected snapshot is excluded from the statistics rather than poisoning the cost estimate.

This is measurement only. It does NOT choose quantity, leverage, protection, or change the
deterministic promotion gate, and it does NOT compute realized PnL. It exists so walk-forward
and cost-stress conclusions can be calibrated against the live venue's real quoted depth
instead of an assumed half-spread.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Iterable

from src.market.orderbook import OrderBook, depth_within_bps
from src.market.orderbook_quality import check_order_book


def summarize_spreads(obs_list: Iterable[OrderBook], *, now_ms: int | None = None,
                      max_age_ms: int = 60_000) -> dict:
    """Aggregate observed spread/depth per symbol, fail-closed on rejected snapshots.

    Every snapshot is judged by ``check_order_book`` (using ``now_ms`` / ``max_age_ms`` for
    freshness; pass an explicit ``now_ms`` to calibrate over recorded snapshots). Any
    rejected snapshot (crossed, empty, non-positive, future-dated, or stale) is excluded
    from the statistics rather than poisoning the cost estimate.

    Returns ``{symbol: stats}`` where stats carries ``n`` (snapshots seen), ``n_valid``
    (passed the gate), ``rejected`` (failed the gate), and, when ``n_valid > 0``:
    ``spread_bps_median``, ``spread_bps_mean``, ``mid_mean``, ``depth_5bps_mean``,
    ``depth_60bps_mean``. When every snapshot for a symbol is rejected, the spread/depth
    fields are ``None`` so the caller cannot mistake "no data" for a cheap market.
    """
    by_sym: dict[str, list[OrderBook]] = defaultdict(list)
    for ob in obs_list:
        by_sym[ob.symbol].append(ob)

    out: dict[str, dict] = {}
    for sym, obs in by_sym.items():
        spreads: list[float] = []
        mids: list[float] = []
        depth5: list[float] = []
        depth60: list[float] = []
        rejected = 0
        for o in obs:
            q = check_order_book(o, now_ms=now_ms, max_age_ms=max_age_ms)
            if not q.ok:
                rejected += 1
                continue
            spreads.append(q.spread_bps)
            mids.append(q.mid)
            depth5.append(depth_within_bps(o, 5.0)["total_depth"])
            depth60.append(depth_within_bps(o, 60.0)["total_depth"])

        if spreads:
            out[sym] = {
                "n": len(obs),
                "n_valid": len(spreads),
                "rejected": rejected,
                "spread_bps_median": statistics.median(spreads),
                "spread_bps_mean": statistics.fmean(spreads),
                "mid_mean": statistics.fmean(mids),
                "depth_5bps_mean": statistics.fmean(depth5),
                "depth_60bps_mean": statistics.fmean(depth60),
            }
        else:
            out[sym] = {
                "n": len(obs),
                "n_valid": 0,
                "rejected": rejected,
                "spread_bps_median": None,
                "spread_bps_mean": None,
                "mid_mean": None,
                "depth_5bps_mean": None,
                "depth_60bps_mean": None,
            }
    return out
