#!/usr/bin/env python3
"""Clean multi-symbol baseline sweep at the real policy notional ($25).

R3: re-evaluate every stored dataset through run_baseline with quantity derived
from `max_position_notional_usd` (NOT the old hardcoded 1.0 contract), so the
symbol/regime breakdown is honest. Zero signed calls, zero orders, public data only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.baseline import BaselineConfig, run_baseline
from src.market.history import data_quality_report, load_dataset, snapshots_from_dataset
from src.evaluation.statistics import compute_statistics
from src.runtime.resource_budget import ResourceBudget
from scripts.resource_guard import GuardPolicy, snapshot as host_snapshot


def sweep(symbol: str, granularity: str, notional: float) -> dict:
    dataset_path = ROOT / "data" / "history" / f"{symbol}_{granularity}.json"
    if not dataset_path.exists():
        return {"symbol": symbol, "granularity": granularity, "error": "no dataset"}
    dataset = load_dataset(dataset_path)
    dq = data_quality_report(dataset)
    if not dq.ok:
        return {"symbol": symbol, "granularity": granularity, "skipped": "DATA_QUALITY", "dq": dq.as_dict()}
    snapshots = snapshots_from_dataset(dataset)
    config = BaselineConfig(fee_bps=5.0, funding_bps=2.0, slippage_bps=2.0,
                            real_funding=True, max_position_notional_usd=notional)
    baseline = run_baseline(snapshots, config)
    stats = compute_statistics(baseline.trade_pnls)
    return {
        "symbol": symbol,
        "granularity": granularity,
        "snapshots": baseline.snapshots,
        "closed_trades": baseline.closed_trades,
        "position_notional_usd": baseline.position_notional_usd,
        "gross_pnl": round(baseline.gross_pnl, 4),
        "fees": round(baseline.fees, 4),
        "spread": round(baseline.spread, 4),
        "slippage": round(baseline.slippage, 4),
        "funding": round(baseline.funding, 4),
        "net_pnl": round(baseline.net_pnl, 4),
        "promotion_allowed": baseline.promotion_allowed,
        "promotion_reason": baseline.promotion_reason,
        "walk_forward_windows": len(baseline.walk_forward_splits),
        "expectancy": stats.get("expectancy"),
        "profit_factor": stats.get("profit_factor"),
        "strategy_breakdown": {k: {"closed_trades": v["closed_trades"], "net_pnl": round(v["net_pnl"], 4)}
                               for k, v in baseline.strategy_breakdown.items()},
        "regime_breakdown": {k: {"closed_trades": v["closed_trades"], "net_pnl": round(v["net_pnl"], 4)}
                             for k, v in baseline.regime_breakdown.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="clean multi-symbol baseline sweep at policy notional")
    parser.add_argument("--notional", type=float, default=25.0)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "phase-33" / "notional-sweep.json")
    parser.add_argument("--symbols", nargs="*", default=None,
                        help="symbol_granularity pairs e.g. BTCUSDT 1m ETHUSDT 1m ... (default: all 8 real symbols)")
    args = parser.parse_args()

    targets = args.symbols or [
        "BTCUSDT 1m", "ETHUSDT 1m", "SOLUSDT 1m", "XRPUSDT 1m",
        "DOGEUSDT 1m", "LINKUSDT 1m", "BNBUSDT 1m", "BTCUSDT 5m", "ETHUSDT 5m",
    ]

    policy = GuardPolicy()
    budget = ResourceBudget(snapshot_source=host_snapshot, policy=policy, sample_interval_seconds=5.0)
    results = []
    with budget:
        for t in targets:
            sym, gran = t.split()
            t0 = time.time()
            r = sweep(sym, gran, args.notional)
            r["elapsed_s"] = round(time.time() - t0, 2)
            results.append(r)
            print(f"{sym} {gran}: closed={r.get('closed_trades')} net_pnl={r.get('net_pnl')} "
                  f"reason={r.get('promotion_reason')} ({r['elapsed_s']}s)", flush=True)

    out = {
        "mode": "real-history-baseline-sweep",
        "notional_usd": args.notional,
        "generated_ms": int(time.time() * 1000),
        "results": results,
        "selection_blocked": True,
        "report_honest": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
