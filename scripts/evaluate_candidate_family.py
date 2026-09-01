#!/usr/bin/env python3
"""Acquire broader real public history and run the measurement-only walk-forward
family-wise robustness across a multi-symbol candidate family.

No signed calls, no credentials, no orders. Pure unauthenticated SUSDT-FUTURES
market data turned into durable datasets, each evaluated through the same
cost-inclusive, walk-forward, robustness-gated engine, then aggregated with the
Bonferroni family-wise multiple-testing correction from phase 11.

Usage:
  python3 scripts/evaluate_candidate_family.py --fetch \
      --output reports/phase-12/candidate-family.json
  # or evaluate only already-stored datasets:
  python3 scripts/evaluate_candidate_family.py --output reports/phase-12/candidate-family.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market.history import (
    HistoryDataset,
    acquire_dataset,
    coverage_gate,
    data_quality_report,
    load_dataset,
    real_funding_readiness,
    snapshots_from_dataset,
)
from src.market.bitget_public import BitgetPublicClient
from src.evaluation.baseline import (
    BaselineConfig,
    evaluate_candidate_family,
    run_baseline,
    run_walk_forward,
    summarize_walk_forward,
)
from src.runtime.resource_budget import ResourceBudget
from scripts.resource_guard import GuardPolicy, snapshot as host_snapshot

# Broaden the candidate family: extend the two existing symbols to longer
# windows and add four more liquid USDT perpetuals so the family-wise
# multiple-testing correction is exercised across a genuinely wider scan.
DEFAULT_CANDIDATES = (
    ("BTCUSDT", "5m", 3000),
    ("ETHUSDT", "5m", 3000),
    ("SOLUSDT", "5m", 3000),
    ("BNBUSDT", "5m", 3000),
    ("XRPUSDT", "5m", 3000),
    ("DOGEUSDT", "5m", 3000),
    ("BTCUSDT", "1m", 2000),
    ("ETHUSDT", "1m", 2000),
)


async def acquire_one(client, symbol, granularity, max_candles, funding_limit, half_spread):
    ds = await acquire_dataset(
        client, symbol, granularity, max_candles=max_candles,
        funding_limit=funding_limit, assumed_half_spread_bps=half_spread,
    )
    path = ROOT / "data" / "history" / f"{symbol}_{granularity}.json"
    path.write_text(json.dumps(ds.to_dict(), indent=2, sort_keys=True) + "\n")
    return ds, path


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward family-wise robustness across real public history")
    parser.add_argument("--fetch", action="store_true", help="download fresh datasets (else use stored)")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "phase-12" / "candidate-family.json")
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--funding-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--max-data-age-ms", type=int, default=None,
                        help="reject a stored dataset whose newest candle is older than this span")
    parser.add_argument("--symbols", type=str, default=None,
                        help="comma-separated 'SYM,GRAN,N' overrides (e.g. BTCUSDT,5m,3000)")
    # Continuous, fail-closed host resource budget. The heavy family-wise replay
    # can run for a long time; abort it (never kill anything) if the host drifts
    # into memory/swap/disk/inode pressure instead of letting it exhaust the host.
    parser.add_argument("--resource-budget", "--no-resource-budget", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="enforce a continuous runtime resource budget (default on)")
    parser.add_argument("--resource-min-memory-mb", type=int, default=None,
                        help="override the minimum available memory (MB) for this run")
    parser.add_argument("--resource-interval", type=float, default=5.0,
                        help="seconds between watchdog samples (watchdog only)")
    parser.add_argument("--resource-watchdog", "--no-resource-watchdog", action=argparse.BooleanOptionalAction,
                        default=False,
                        help="run a background watchdog that samples host resources during the run")
    args = parser.parse_args()

    if args.symbols:
        cands = []
        for part in args.symbols.split(","):
            s, g, n = part.strip().split(":")
            cands.append((s, g, int(n)))
    else:
        cands = DEFAULT_CANDIDATES

    config = BaselineConfig(fee_bps=args.fee_bps, funding_bps=args.funding_bps,
                            slippage_bps=args.slippage_bps, real_funding=True)

    # Continuous, fail-closed runtime resource budget for the heavy family-wise
    # replay below. It only observes host state and raises; it never kills or
    # restarts Hermes, deployed bots, databases, or unrelated services.
    budget: "ResourceBudget | None" = None
    if args.resource_budget:
        policy = GuardPolicy()
        if args.resource_min_memory_mb is not None:
            policy = GuardPolicy(min_available_memory_mb=args.resource_min_memory_mb)
        budget = ResourceBudget(snapshot_source=host_snapshot, policy=policy,
                                sample_interval_seconds=args.resource_interval,
                                watchdog=args.resource_watchdog)

    acquired: list[tuple[str, list, HistoryDataset]] = []
    net_metrics = Counter()
    latency: list[float] = []
    fetch_errors: list[dict] = []

    for symbol, granularity, max_candles in cands:
        key = f"{symbol}_{granularity}"
        client = None
        try:
            if args.fetch:
                client = BitgetPublicClient(venue="bitget", product_type="SUSDT-FUTURES")
                ds, path = asyncio.run(acquire_one(client, symbol, granularity, max_candles,
                                                    funding_limit=300, half_spread=0.5))
                m = client.metrics
                net_metrics["requests"] += m.requests
                net_metrics["successes"] += m.successes
                net_metrics["failures"] += m.failures
                net_metrics["rate_limits"] += m.rate_limits
                net_metrics["retries"] += m.retries
                net_metrics["schema_rejections"] += m.schema_rejections
                net_metrics["policy_rejections"] += m.policy_rejections
                latency.extend(m.latency_ms or [])
            else:
                path = ROOT / "data" / "history" / f"{key}.json"
                if not path.exists():
                    fetch_errors.append({"symbol": symbol, "granularity": granularity,
                                          "error": "stored dataset missing; pass --fetch"})
                    continue
                ds = load_dataset(path)
        except Exception as e:  # acquisition can transiently fail; record, keep going
            fetch_errors.append({"symbol": symbol, "granularity": granularity,
                                 "error": f"{type(e).__name__}: {str(e)[:200]}"})
            continue

        # Fail closed on structurally unsound datasets before any evaluation.
        dq = data_quality_report(ds, max_data_age_ms=args.max_data_age_ms)
        stale_rejected = args.max_data_age_ms is not None and not dq.freshness_ok
        if not dq.ok or stale_rejected:
            fetch_errors.append({"symbol": symbol, "granularity": granularity,
                                 "error": f"DATA_QUALITY_REJECTED dup={dq.duplicate_timestamps} "
                                          f"nonchrono={dq.non_chronological} bad={dq.bad_prices} "
                                          f"fund_anom={dq.funding_anomalies} age_ms={dq.data_age_ms} "
                                          f"fresh={dq.freshness_ok}"})
            continue
        readiness = real_funding_readiness(ds, dq)
        if not readiness.ok:
            fetch_errors.append({"symbol": symbol, "granularity": granularity,
                                 "error": f"FUNDING_COVERAGE_REJECTED: {readiness.reason}"})
            continue

        acquired.append((key, ds, snapshots_from_dataset(ds)))

    if not acquired:
        print("NO_USABLE_DATASETS", json.dumps(fetch_errors), file=sys.stderr)
        return 4

    # Fail-closed: park heavy evaluation when the blessed corpus is stale
    # (directive §11 automation contract). We cannot run trustworthy
    # evaluation on a stale corpus, so we park rather than produce a
    # questionable result.
    from scripts.heartbeat_status import assemble_status, should_park_heavy_work
    if should_park_heavy_work(assemble_status()):
        print("CORPUS_STALE_PARKED: corpus freshness stale; heavy evaluation parked fail-closed", file=sys.stderr)
        return 8

    # Measurement-only family-wise robustness across the acquired candidate family.
    candidates = [(key, snaps) for key, _ds, snaps in acquired]
    family = evaluate_candidate_family(
        candidates, config,
        min_closed_trades=args.min_closed_trades, confidence=args.confidence,
        resource_budget=budget,
    )

    # Also keep per-candidate walk-forward summaries for the report (honest facts).
    per_candidate_summary = []
    for key, ds, snaps in acquired:
        if budget is not None:
            budget.assert_within()
        wf = run_walk_forward(snaps, config)
        baseline = run_baseline(snaps, config)
        per_candidate_summary.append({
            "name": key,
            "symbol": ds.symbol, "granularity": ds.granularity,
            "candles": len(ds.candles), "funding_records": len(ds.funding),
            "walk_forward_summary": summarize_walk_forward(wf),
            "baseline_net_pnl": round(baseline.net_pnl, 4),
            "baseline_closed_trades": baseline.closed_trades,
            "baseline_promotion_reason": baseline.promotion_reason,
        })

    payload = {
        "source": "bitget-public-history",
        "endpoint": "https://api.bitget.com/api/v2/mix/market/{candles,history-fund-rate}",
        "request_evidence": {
            "mode": "fetch" if args.fetch else "stored-dataset",
            "requests": net_metrics.get("requests", 0),
            "successes": net_metrics.get("successes", 0),
            "failures": net_metrics.get("failures", 0),
            "rate_limits": net_metrics.get("rate_limits", 0),
            "retries": net_metrics.get("retries", 0),
            "schema_rejections": net_metrics.get("schema_rejections", 0),
            "policy_rejections": net_metrics.get("policy_rejections", 0),
            "latency_ms_sample": [round(x, 2) for x in latency[:50]],
            "signed_calls": 0,
            "orders": 0,
            "credentials_used": False,
        },
        "config": {"fee_bps": args.fee_bps, "funding_bps": args.funding_bps,
                   "slippage_bps": args.slippage_bps, "min_closed_trades": args.min_closed_trades,
                   "confidence": args.confidence},
        "candidates_acquired": len(acquired),
        "fetch_errors": fetch_errors,
        "per_candidate_summary": per_candidate_summary,
        "family_wise": family,
        "deterministic_baseline_gate": "NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")

    # Human-readable summary to stdout.
    print(json.dumps({
        "candidates": family["candidates"],
        "fetch_errors": len(fetch_errors),
        "network_requests": net_metrics.get("requests", 0),
        "family_wise_tests": family["family_wise"]["tests"],
        "uncorrected_positives": family["family_wise"]["uncorrected_positives"],
        "corrected_positives": family["family_wise"]["corrected_positives"],
        "any_corrected_positive": family["family_wise"]["any_corrected_positive"],
        "total_closed_trades": family["total_closed_trades"],
        "family_adequate_sample": family["family_adequate_sample"],
        "selection_blocked": family["selection_blocked"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
