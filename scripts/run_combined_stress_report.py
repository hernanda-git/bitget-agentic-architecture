#!/usr/bin/env python3
"""Phase-10 combined-stress report generator (measurement only, fail-closed).

Runs the realistic simultaneous adverse-cost stress (fee + funding + slippage
moving together) and the walk-forward robustness gate across all four stored
public-history datasets. No network, no credentials, no orders, no selection.

Verification command (network-free, secret-free, re-runnable):
  python3 scripts/run_combined_stress_report.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market.history import (
    data_quality_report,
    load_dataset,
    real_funding_readiness,
    snapshots_from_dataset,
)
from src.evaluation.baseline import (
    BaselineConfig,
    gate_walk_forward_robustness,
    run_baseline,
    run_walk_forward,
)
from src.evaluation.stress import run_combined_stress

DATASETS = [
    ("BTCUSDT", "1m"),
    ("BTCUSDT", "5m"),
    ("ETHUSDT", "1m"),
    ("ETHUSDT", "5m"),
]


def evaluate_one(symbol: str, granularity: str) -> dict:
    path = ROOT / "data" / "history" / f"{symbol}_{granularity}.json"
    dataset = load_dataset(path)
    dq = data_quality_report(dataset)
    readiness = real_funding_readiness(dataset, dq)
    snapshots = snapshots_from_dataset(dataset)
    config = BaselineConfig(fee_bps=5.0, funding_bps=2.0, slippage_bps=2.0, real_funding=True)

    baseline = run_baseline(snapshots, config)
    walk_forward = run_walk_forward(snapshots, config)
    combined = run_combined_stress(snapshots, config)
    gate = gate_walk_forward_robustness(
        walk_forward, trade_pnls=baseline.trade_pnls, min_closed_trades=30
    )

    # Fail-closed invariant checks (the whole point of this report).
    invariant = {
        "combined_never_adds_trades": combined["closed_trades"] <= baseline.closed_trades,
        "combined_promotion_blocked": combined["promotion_allowed"] is False,
        "gate_selection_blocked": gate["selection_blocked"] is True,
        "gate_expectancy_positive_with_ci_false": gate["expectancy_positive_with_ci"] is False,
    }

    return {
        "symbol": symbol, "granularity": granularity,
        "data_quality": {
            "ok": dq.ok, "candle_count": dq.candle_count, "gaps": len(dq.gaps),
            "max_missing_bars": dq.max_missing_bars, "zero_volume_bars": dq.zero_volume_bars,
            "funding_missing": dq.funding_missing, "funding_anomalies": dq.funding_anomalies,
            "data_age_ms": dq.data_age_ms,
            "max_single_bar_return_bps": round(dq.max_single_bar_return_bps, 2),
            "freshness_ok": dq.freshness_ok,
        },
        "funding_readiness_ok": readiness.ok,
        "baseline": {
            "closed_trades": baseline.closed_trades, "gross_pnl": round(baseline.gross_pnl, 4),
            "fees": round(baseline.fees, 4), "spread": round(baseline.spread, 4),
            "slippage": round(baseline.slippage, 4), "funding": round(baseline.funding, 4),
            "net_pnl": round(baseline.net_pnl, 4), "promotion_reason": baseline.promotion_reason,
        },
        "combined_stress": {
            "dimension": combined["dimension"],
            "fee_bps": combined["fee_bps"], "funding_bps": combined["funding_bps"],
            "slippage_bps": combined["slippage_bps"],
            "closed_trades": combined["closed_trades"],
            "gross_pnl": round(combined["gross_pnl"], 4), "fees": round(combined["fees"], 4),
            "spread": round(combined["spread"], 4), "slippage": round(combined["slippage"], 4),
            "funding": round(combined["funding"], 4), "net_pnl": round(combined["net_pnl"], 4),
            "drawdown": round(combined["drawdown"], 4),
            "promotion_allowed": combined["promotion_allowed"],
            "promotion_status": combined["promotion_status"],
            "baseline_closed_trades": combined["baseline_closed_trades"],
        },
        "walk_forward_robustness": {
            "adequate_sample": gate["adequate_sample"],
            "total_closed_trades": gate["total_closed_trades"],
            "expectancy_mean": round(gate["expectancy_mean"], 6),
            "expectancy_ci": [round(x, 6) for x in gate["expectancy_ci"]],
            "expectancy_positive_with_ci": gate["expectancy_positive_with_ci"],
            "selection_blocked": gate["selection_blocked"],
        },
        "invariant": invariant,
        "invariant_all_pass": all(invariant.values()),
    }


def main() -> int:
    results = [evaluate_one(s, g) for s, g in DATASETS]
    all_pass = all(r["invariant_all_pass"] for r in results)
    payload = {
        "task": "realistic combined cost/funding/slippage stress + fail-closed stress-invariance across stored public history",
        "phase": "phase-10 (combined-stress continuation; selection remains blocked)",
        "generated_at_timezone": "Asia/Jakarta",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0, "signed_calls": 0, "orders": 0, "positions": 0,
        "selection_blocked": True,
        "datasets": results,
        "invariant_all_pass": all_pass,
        "limitations": [
            "Stored public history (2000 candles/symbol/granularity) is a fixed historical snapshot; no live stream.",
            "Historical bid/ask was unavailable from the public API; spread remains an explicit assumed half-spread (0.5 bps), never an observed quote claim.",
            "Evaluation uses FakeExchange only; no signed/demo/testnet execution occurred, so no venue reconciliation or protection read-back is possible.",
            "The combined stress is measurement only and never changes the deterministic promotion gate (still NEGATIVE_NET_PNL).",
            "Public unauthenticated history does not establish live venue reconciliation; the negative baseline is a deterministic cost-inclusive replay result, not a live trading outcome.",
            "No strategy was selected, ranked, or promoted; selection_blocked remains True throughout.",
        ],
    }
    out_dir = ROOT / "reports" / "phase-10" / "combined-stress"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"{'SYM':8} {'GRAN':5} {'BASE_NET':>12} {'CMB_NET':>12} {'CLOSED':>7} {'BLK':>4} {'INV':>4}")
    for r in results:
        b = r["baseline"]["net_pnl"]; c = r["combined_stress"]["net_pnl"]
        blk = "Y" if r["walk_forward_robustness"]["selection_blocked"] else "N"
        inv = "PASS" if r["invariant_all_pass"] else "FAIL"
        print(f"{r['symbol']:8} {r['granularity']:5} {b:>12.2f} {c:>12.2f} "
              f"{r['baseline']['closed_trades']:>7} {blk:>4} {inv:>4}")
    print(f"\ninvariant_all_pass={all_pass}  report -> {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
