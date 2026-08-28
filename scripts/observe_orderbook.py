"""Observed order-book cost-surface calibration (read-only public venue depth).

Drives ``BitgetPublicClient.get_order_book`` over a set of symbols, gathering N snapshots
each, and aggregates them through the fail-closed ``summarize_spreads`` gate to produce a
real-venue spread/depth table. This replaces the previously *assumed* half-spread in cost
models with observed quoted depth, so walk-forward and cost-stress conclusions can be
calibrated against the live venue.

This is measurement ONLY:
- Uses the unauthenticated public orderbook endpoint (no keys, no signing).
- Places no orders, changes no leverage/protection, and does not compute realized PnL.
- Does not change the deterministic promotion gate (Phase 6 remains blocked on a negative
  baseline regardless of what the observed spread turns out to be).

Usage:
    python3 scripts/observe_orderbook.py --symbols BTCUSDT,ETHUSDT --snapshots 4 --limit 20
    python3 scripts/observe_orderbook.py --from-manifest data/history/corpus_manifest.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market.bitget_public import BitgetPublicClient, PublicMarketError
from src.market.orderbook_calibration import summarize_spreads


async def run_calibration(symbols: Sequence[str], *, snapshots_per_symbol: int = 3,
                          limit: int = 20, min_interval_seconds: float = 0.2,
                          client: BitgetPublicClient | None = None) -> dict:
    """Gather ``snapshots_per_symbol`` order books per symbol and aggregate them.

    Fail-closed: a symbol that errors on every snapshot (schema/values rejection from the
    gate) contributes no observations and is omitted from the result rather than presented
    as a cheap market. Network errors per snapshot are swallowed per-symbol so one bad
    symbol cannot abort the whole calibration.
    """
    own_client = client is None
    if client is None:
        client = BitgetPublicClient(min_interval_seconds=min_interval_seconds)
    obs = []
    try:
        for sym in symbols:
            for _ in range(snapshots_per_symbol):
                try:
                    ob = await client.get_order_book(sym, limit=limit)
                except PublicMarketError:
                    break  # fail-closed per symbol: no valid snapshot -> skip symbol
                obs.append(ob)
                if min_interval_seconds > 0:
                    await asyncio.sleep(min_interval_seconds)
    finally:
        # The public client opens a fresh httpx client per request and closes it itself,
        # so there is no persistent handle to release here.
        pass
    return summarize_spreads(obs)


def _load_symbols_from_manifest(manifest_path: str) -> list[str]:
    data = json.loads(Path(manifest_path).read_text())
    return [entry["symbol"] for entry in data.get("datasets", [])]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observed order-book spread/deth calibration (read-only).")
    parser.add_argument("--symbols", help="comma-separated symbols, e.g. BTCUSDT,ETHUSDT")
    parser.add_argument("--from-manifest", help="read symbols from a corpus manifest JSON")
    parser.add_argument("--snapshots", type=int, default=3, help="snapshots per symbol")
    parser.add_argument("--limit", type=int, default=20, help="order-book depth limit")
    parser.add_argument("--interval", type=float, default=0.2, help="min seconds between requests")
    parser.add_argument("--out", default="reports/orderbook_calibration.json",
                        help="output JSON path for the calibration table")
    args = parser.parse_args(argv)

    if args.symbols:
        symbols: list[str] = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    elif args.from_manifest:
        symbols = _load_symbols_from_manifest(args.from_manifest)
    else:
        print("error: provide --symbols or --from-manifest", file=sys.stderr)
        return 2

    if not symbols:
        print("error: no symbols resolved", file=sys.stderr)
        return 2

    result = asyncio.run(run_calibration(
        symbols, snapshots_per_symbol=args.snapshots, limit=args.limit,
        min_interval_seconds=args.interval,
    ))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_ms": int(time.time() * 1000),
        "mode": "observed-public-orderbook (read-only, no execution)",
        "symbols": symbols,
        "snapshots_per_symbol": args.snapshots,
        "limit": args.limit,
        "calibration": result,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
