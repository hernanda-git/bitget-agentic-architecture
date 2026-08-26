#!/usr/bin/env python3
"""Per-strategy walk-forward attribution on real public history (no signed calls).

This is MEASUREMENT ONLY. It never selects, ranks, or promotes a strategy; the
result always carries ``selection_blocked: true`` so the test set cannot be
peeked to choose a winner. It is the strategy-attribution companion to
``evaluate_real_history.py`` and shares its fail-closed data-quality gate.

Usage:
  # stored dataset
  python3 scripts/run_strategy_attribution.py --dataset data/history/BTCUSDT_5m.json
  # fresh unauthenticated public fetch
  python3 scripts/run_strategy_attribution.py --symbol BTCUSDT --granularity 5m --max-candles 2000 --fetch
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.baseline import BaselineConfig, run_strategy_attribution
from src.market.bitget_public import BitgetPublicClient
from src.market.history import acquire_dataset, data_quality_report, load_dataset, snapshots_from_dataset


async def _fetch(args: argparse.Namespace):
    client = BitgetPublicClient(venue="bitget", product_type="SUSDT-FUTURES")
    end_time_ms = int(args.end_time_ms) if args.end_time_ms else int(time.time() * 1000)
    dataset = await acquire_dataset(
        client, args.symbol, args.granularity, end_time_ms=end_time_ms,
        max_candles=args.max_candles, funding_limit=args.funding_limit,
        assumed_half_spread_bps=args.assumed_half_spread_bps,
    )
    out_dir = ROOT / "data" / "history"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.symbol}_{args.granularity}.json"
    path.write_text(json.dumps(dataset.to_dict(), indent=2, sort_keys=True) + "\n")
    print(f"stored {len(dataset.candles)} candles -> {path}")
    return dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-strategy walk-forward attribution on public history")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--granularity", default="5m")
    parser.add_argument("--max-candles", type=int, default=2000)
    parser.add_argument("--funding-limit", type=int, default=200)
    parser.add_argument("--assumed-half-spread-bps", type=float, default=0.5)
    parser.add_argument("--end-time-ms", type=int, default=0)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "phase-5" / "strategy-attribution.json")
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--funding-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    args = parser.parse_args()

    if args.fetch and args.dataset:
        parser.error("use --fetch OR --dataset, not both")
    if args.dataset is None and not args.fetch:
        candidate = ROOT / "data" / "history" / f"{args.symbol}_{args.granularity}.json"
        if candidate.exists():
            args.dataset = candidate
        else:
            parser.error("no stored dataset found; pass --fetch or --dataset")

    if args.fetch:
        dataset = asyncio.run(_fetch(args))
    else:
        dataset = load_dataset(args.dataset)
        print(f"loaded {len(dataset.candles)} candles + {len(dataset.funding)} funding records from {args.dataset}")

    dq = data_quality_report(dataset)
    if not dq.ok:
        print(f"DATA_QUALITY_REJECTED: {dq.as_dict()}", file=sys.stderr)
        return 2

    snapshots = snapshots_from_dataset(dataset)
    config = BaselineConfig(fee_bps=args.fee_bps, funding_bps=args.funding_bps,
                            slippage_bps=args.slippage_bps, real_funding=True)
    attribution = run_strategy_attribution(snapshots, config)

    payload = {
        "source": "bitget-public-history",
        "symbol": dataset.symbol, "product_type": dataset.product_type,
        "granularity": dataset.granularity,
        "candles": len(dataset.candles), "funding_records": len(dataset.funding),
        "config": {"fee_bps": args.fee_bps, "funding_bps": args.funding_bps, "slippage_bps": args.slippage_bps},
        "data_quality": dq.as_dict(),
        "network_calls": 0, "signed_calls": 0, "orders": 0, "positions": 0,
        "strategy_attribution": attribution,
        "selection_blocked": attribution["selection_blocked"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")

    print(json.dumps({
        "symbol": dataset.symbol, "granularity": dataset.granularity,
        "candles": len(dataset.candles),
        "selection_blocked": attribution["selection_blocked"],
        "per_strategy": {
            name: {
                "windows": attribution[name]["windows"],
                "windows_with_trades": attribution[name]["windows_with_trades"],
                "profitable_windows": attribution[name]["profitable_windows"],
                "closed_trades": attribution[name]["closed_trades"],
                "total_net_pnl": round(attribution[name]["total_net_pnl"], 4),
            } for name in attribution["strategies_evaluated"]
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
