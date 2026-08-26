#!/usr/bin/env python3
"""Acquire public historical data and run the deterministic baseline on it.

No signed calls, no credentials, no orders. Pure unauthenticated market data
(SUSDT-FUTURES demo product type) turned into a durable dataset, then evaluated
through the same cost-inclusive, walk-forward, stress-tested engine used for the
synthetic fixture.

Usage:
  # fetch + evaluate in one step
  python3 scripts/evaluate_real_history.py --symbol BTCUSDT --granularity 1m \
      --max-candles 1500 --fetch --output reports/phase-5/real-data-baseline.json
  # evaluate a previously stored dataset
  python3 scripts/evaluate_real_history.py --dataset data/history/BTCUSDT_1m.json \
      --output reports/phase-5/real-data-baseline.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market.history import acquire_dataset, data_quality_report, load_dataset, snapshots_from_dataset
from src.market.bitget_public import BitgetPublicClient
from src.evaluation.baseline import (
    BaselineConfig,
    run_baseline,
    run_cost_stress,
    run_coverage_variants,
    run_strategy_attribution,
    run_walk_forward,
    summarize_walk_forward,
)


async def fetch_dataset(args: argparse.Namespace):
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
    print(f"stored {len(dataset.candles)} candles + {len(dataset.funding)} funding records -> {path}")
    return dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate deterministic baseline on real public history")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--granularity", default="1m")
    parser.add_argument("--max-candles", type=int, default=1500)
    parser.add_argument("--funding-limit", type=int, default=200)
    parser.add_argument("--assumed-half-spread-bps", type=float, default=0.5)
    parser.add_argument("--end-time-ms", type=int, default=0)
    parser.add_argument("--fetch", action="store_true", help="download a fresh dataset")
    parser.add_argument("--dataset", type=Path, default=None, help="evaluate a stored dataset instead")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "phase-5" / "real-data-baseline.json")
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--funding-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--max-data-age-ms", type=int, default=None,
                        help="if set, reject the dataset when the newest candle is older "
                             "than the fetch time by more than this span (freshness gate)")
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
        dataset = asyncio.run(fetch_dataset(args))
    else:
        dataset = load_dataset(args.dataset)
        print(f"loaded {len(dataset.candles)} candles + {len(dataset.funding)} funding records from {args.dataset}")

    # Fail closed on structurally unsound datasets before any evaluation.
    dq = data_quality_report(dataset, max_data_age_ms=args.max_data_age_ms)
    stale_rejected = args.max_data_age_ms is not None and not dq.freshness_ok
    if not dq.ok or stale_rejected:
        message = (
            f"DATA_QUALITY_REJECTED: duplicate_timestamps={dq.duplicate_timestamps} "
            f"non_chronological={dq.non_chronological} bad_prices={dq.bad_prices} "
            f"funding_anomalies={dq.funding_anomalies} data_age_ms={dq.data_age_ms} "
            f"freshness_ok={dq.freshness_ok}"
        )
        print(message, file=sys.stderr)
        return 2
    print(
        f"data quality ok: candles={dq.candle_count} gaps={len(dq.gaps)} "
        f"max_missing_bars={dq.max_missing_bars} zero_volume_bars={dq.zero_volume_bars} "
        f"funding_missing={dq.funding_missing} data_age_ms={dq.data_age_ms} "
        f"max_single_bar_return_bps={round(dq.max_single_bar_return_bps, 2)} "
        f"funding_anomalies={dq.funding_anomalies}"
    )

    snapshots = snapshots_from_dataset(dataset)
    config = BaselineConfig(fee_bps=args.fee_bps, funding_bps=args.funding_bps, slippage_bps=args.slippage_bps, real_funding=True)
    baseline = run_baseline(snapshots, config)
    walk_forward = run_walk_forward(snapshots, config)
    cost_stress = run_cost_stress(snapshots, config)
    coverage_variants = run_coverage_variants(snapshots, config, coverages=(1.0, 2.0, 3.0))
    strategy_attribution = run_strategy_attribution(snapshots, config)

    payload = {
        "source": "bitget-public-history",
        "symbol": dataset.symbol, "product_type": dataset.product_type, "granularity": dataset.granularity,
        "fetched_at_ms": dataset.fetched_at_ms, "assumed_half_spread_bps": dataset.assumed_half_spread_bps,
        "funding_records": len(dataset.funding), "candles": len(dataset.candles),
        "config": {"fee_bps": args.fee_bps, "funding_bps": args.funding_bps, "slippage_bps": args.slippage_bps},
        "data_quality": dq.as_dict(),
        "baseline": {k: list(v) if isinstance(v, tuple) else v for k, v in baseline.__dict__.items()},
        "walk_forward": [dict(r) for r in walk_forward],
        "walk_forward_summary": summarize_walk_forward(walk_forward),
        "cost_stress": [dict(r) for r in cost_stress],
        "cost_coverage_variants": [dict(r) for r in coverage_variants],
        "strategy_attribution": strategy_attribution,
        "snapshot_time_range": {
            "first_ms": snapshots[0].source_ts_ms, "last_ms": snapshots[-1].source_ts_ms,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps({
        "snapshots": len(snapshots), "closed_trades": baseline.closed_trades,
        "cost_gate_skipped": baseline.cost_gate_skipped,
        "gross_pnl": round(baseline.gross_pnl, 4), "fees": round(baseline.fees, 4),
        "spread": round(baseline.spread, 4), "slippage": round(baseline.slippage, 4),
        "funding": round(baseline.funding, 4), "net_pnl": round(baseline.net_pnl, 4),
        "promotion_allowed": baseline.promotion_allowed, "reason": baseline.promotion_reason,
        "walk_forward_windows": len(walk_forward),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
