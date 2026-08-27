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

from src.market.history import (
    acquire_dataset,
    data_quality_report,
    load_dataset,
    real_funding_readiness,
    snapshots_from_dataset,
)
from src.market.bitget_public import BitgetPublicClient
from src.evaluation.baseline import (
    BaselineConfig,
    gate_walk_forward_robustness,
    run_baseline,
    run_cost_stress,
    run_coverage_variants,
    run_strategy_attribution,
    run_walk_forward,
    summarize_walk_forward,
)
from src.evaluation.stress import run_stress_matrix, run_combined_stress
from src.evaluation.statistics import compute_statistics
from src.evaluation.walk_forward_quality import gate_walk_forward_dataset
from src.evaluation.report_honesty import ReportHonestyError, assert_truthful
from src.runtime.resource_budget import ResourceBudget
from scripts.resource_guard import GuardPolicy, snapshot as host_snapshot


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
    return dataset, client


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
    parser.add_argument("--resource-budget", "--no-resource-budget", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="enforce a continuous runtime resource budget (default on)")
    parser.add_argument("--resource-min-memory-mb", type=int, default=None,
                        help="override the minimum available memory (MB) for this run")
    parser.add_argument("--resource-max-swap-percent", type=float, default=None,
                        help="override the max swap-used percentage (default 90.0); relax "
                             "knowingly on a constrained host instead of fully disabling the budget")
    parser.add_argument("--resource-interval", type=float, default=5.0,
                        help="seconds between watchdog samples (watchdog only)")
    parser.add_argument("--resource-watchdog", "--no-resource-watchdog", action=argparse.BooleanOptionalAction,
                        default=False,
                        help="run a background watchdog that samples host resources during the run")
    args = parser.parse_args()

    if args.fetch and args.dataset:
        parser.error("use --fetch OR --dataset, not both")
    if args.dataset is None and not args.fetch:
        candidate = ROOT / "data" / "history" / f"{args.symbol}_{args.granularity}.json"
        if candidate.exists():
            args.dataset = candidate
        else:
            parser.error("no stored dataset found; pass --fetch or --dataset")

    client = None
    if args.fetch:
        dataset, client = asyncio.run(fetch_dataset(args))
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
            f"funding_anomalies={dq.funding_anomalies} future_dated={dq.future_dated} "
            f"data_age_ms={dq.data_age_ms} freshness_ok={dq.freshness_ok}"
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

    # Fail closed on any walk-forward window that contains a gap or bad price.
    # A global data-quality pass can hide a hole inside a single test window,
    # and we trade on those windows, so each must be structurally sound and
    # gap-free. This runs before the heavy replay so a holey dataset is
    # rejected without inventing any trade.
    wf_quality = gate_walk_forward_dataset(dataset, config, max_missing_fraction=0.25)
    if not wf_quality.all_ok:
        print(f"WALK_FORWARD_QUALITY_REJECTED: {wf_quality.reject_reason}", file=sys.stderr)
        return 4
    print(f"walk-forward window quality ok: windows={wf_quality.windows}, failed={wf_quality.failed_windows}")

    # Continuous, fail-closed runtime resource budget for the heavy multi-engine
    # replay below. It only observes host state and raises; it never kills or
    # restarts Hermes, deployed bots, databases, or unrelated services.
    budget = None
    if args.resource_budget:
        overrides: dict = {}
        if args.resource_min_memory_mb is not None:
            overrides["min_available_memory_mb"] = args.resource_min_memory_mb
        if args.resource_max_swap_percent is not None:
            overrides["max_swap_used_percent"] = args.resource_max_swap_percent
        policy = GuardPolicy(**overrides) if overrides else GuardPolicy()
        budget = ResourceBudget(snapshot_source=host_snapshot, policy=policy,
                                sample_interval_seconds=args.resource_interval,
                                watchdog=args.resource_watchdog)

    # Fail closed when real funding is requested but the dataset has no usable
    # funding coverage: unmodeled funding is not the same as free funding.
    readiness = real_funding_readiness(dataset, dq)
    if not readiness.ok:
        print(
            f"FUNDING_COVERAGE_REJECTED: {readiness.reason} "
            f"in_range={readiness.funding_records_in_range} "
            f"expected_settlements={readiness.expected_settlements} "
            f"missing={readiness.funding_missing}",
            file=sys.stderr,
        )
        return 3

    class _NoBudget:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
    _ctx = budget if budget is not None else _NoBudget()
    with _ctx:
        baseline = run_baseline(snapshots, config)
        walk_forward = run_walk_forward(snapshots, config)
        cost_stress = run_cost_stress(snapshots, config)
        coverage_variants = run_coverage_variants(snapshots, config, coverages=(1.0, 2.0, 3.0))
        strategy_attribution = run_strategy_attribution(snapshots, config)
        stress_matrix = run_stress_matrix(snapshots, config)
        # Realistic simultaneous adverse-cost stress (fee + funding + slippage move
        # together). Measurement only; never flips the deterministic promotion gate.
        combined_stress = run_combined_stress(snapshots, config)
        statistics = compute_statistics(baseline.trade_pnls)
        # Measurement-only robustness gate: reports adequate-sample and positive
        # expectancy-with-CI facts. Never changes the deterministic promotion gate.
        walk_forward_robustness = gate_walk_forward_robustness(
            walk_forward, trade_pnls=baseline.trade_pnls, min_closed_trades=30
        )

    payload = {
        "source": "bitget-public-history",
        "endpoint": "https://api.bitget.com/api/v2/mix/market/{candles,history-fund-rate}",
        "request_evidence": {
            "mode": "fetch" if client is not None else "stored-dataset",
            "requests": client.metrics.requests if client is not None else 0,
            "successes": client.metrics.successes if client is not None else 0,
            "failures": client.metrics.failures if client is not None else 0,
            "rate_limits": client.metrics.rate_limits if client is not None else 0,
            "retries": client.metrics.retries if client is not None else 0,
            "schema_rejections": client.metrics.schema_rejections if client is not None else 0,
            "policy_rejections": client.metrics.policy_rejections if client is not None else 0,
            "latency_ms": list(client.metrics.latency_ms or []) if client is not None else [],
            "signed_calls": 0,
            "orders": 0,
            "credentials_used": False,
        },
        "symbol": dataset.symbol, "product_type": dataset.product_type, "granularity": dataset.granularity,
        "fetched_at_ms": dataset.fetched_at_ms, "assumed_half_spread_bps": dataset.assumed_half_spread_bps,
        "funding_records": len(dataset.funding), "candles": len(dataset.candles),
        "config": {"fee_bps": args.fee_bps, "funding_bps": args.funding_bps, "slippage_bps": args.slippage_bps},
        "data_quality": dq.as_dict(),
        "funding_readiness": readiness.as_dict(),
        "walk_forward_window_quality": wf_quality.as_dict(),
        "baseline": {k: list(v) if isinstance(v, tuple) else v for k, v in baseline.__dict__.items()},
        "walk_forward": [dict(r) for r in walk_forward],
        "walk_forward_summary": summarize_walk_forward(walk_forward),
        "walk_forward_robustness": walk_forward_robustness,
        "cost_stress": [dict(r) for r in cost_stress],
        "cost_coverage_variants": [dict(r) for r in coverage_variants],
        "strategy_attribution": strategy_attribution,
        "stress_matrix": [dict(r) for r in stress_matrix],
        "combined_stress": dict(combined_stress),
        "statistics": statistics,
        "snapshot_time_range": {
            "first_ms": snapshots[0].source_ts_ms, "last_ms": snapshots[-1].source_ts_ms,
        },
    }
    # Fail-closed honesty anchor: the deterministic promotion gate is
    # NEGATIVE_NET_PNL and selection is always blocked in this repo, so every
    # emitted report must carry that fact and must never contain a
    # promotion/winner/positive-verdict overclaim. This mirrors the phase-15
    # wiring in run_strategy_baseline.py and closes the dashboard-truthfulness
    # parity gap for the real-history entrypoint. The guard runs BEFORE the
    # report is written so any overclaim aborts without emitting a go-live-looking
    # artifact. It never edits the report, never promotes, never selects, and
    # never changes the deterministic gate.
    payload["selection_blocked"] = True
    payload["report_honest"] = True
    try:
        assert_truthful(payload)
    except ReportHonestyError as exc:
        print(f"REPORT_HONESTY_REJECTED: {exc}", file=sys.stderr)
        return 5
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
