#!/usr/bin/env python3
"""Report the full cost sensitivity envelope for one or more local public datasets.

Pure offline evaluation. No network egress, no signing, no credentials. It runs
``cost_envelope_sweep`` (independent fee/funding/slippage grid) over already-stored
public history and prints a consolidated JSON envelope to stdout. The envelope
always carries ``selection_blocked=True`` / ``promotion_blocked=True``; the script
fails closed (non-zero exit) if either is ever False, so it can never launder a
positive verdict into a go-live claim.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.baseline import BaselineConfig
from src.evaluation.cost_sensitivity import cost_envelope_sweep
from src.market.history import load_dataset, snapshots_from_dataset

DEFAULT_SYMBOLS = ("BTCUSDT",)


def run_one(symbol: str, *, fee_mults, funding_mults, slippage_mults, real_funding: bool) -> dict:
    path = ROOT / "data" / "history" / f"{symbol}_1m.json"
    if not path.exists():
        raise SystemExit(f"missing local history: {path}")
    snapshots = snapshots_from_dataset(load_dataset(path))
    cfg = BaselineConfig(real_funding=real_funding)
    res = cost_envelope_sweep(
        snapshots, cfg,
        fee_mults=fee_mults, funding_mults=funding_mults, slippage_mults=slippage_mults,
    )
    # Fail closed: the envelope may never flip the gated promotion state.
    if not res["selection_blocked"] or not res["promotion_blocked"]:
        raise SystemExit(f"envelope for {symbol} left the promotion gate open")
    return {
        "symbol": symbol,
        "n_snapshots": len(snapshots),
        "real_funding": real_funding,
        "n_cells": res["n_cells"],
        "baseline_net": res["baseline_net"],
        "baseline_closed_trades": res["baseline_closed_trades"],
        "min_net": res["min_net"],
        "max_net": res["max_net"],
        "median_net": res["median_net"],
        "worst_cell": {k: res["worst_cell"][k] for k in ("fee_mult", "funding_mult", "slippage_mult", "net_pnl")},
        "best_cell": {k: res["best_cell"][k] for k in ("fee_mult", "funding_mult", "slippage_mult", "net_pnl")},
        "any_profitable": res["any_profitable"],
        "all_blocked": res["all_blocked"],
        "selection_blocked": res["selection_blocked"],
        "promotion_blocked": res["promotion_blocked"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    ap.add_argument("--real-funding", action="store_true")
    ap.add_argument("--fee-mults", nargs="+", type=float, default=(1.0, 2.0))
    ap.add_argument("--funding-mults", nargs="+", type=float, default=(1.0, 2.0))
    ap.add_argument("--slippage-mults", nargs="+", type=float, default=(1.0, 2.0))
    args = ap.parse_args()

    out = []
    for sym in args.symbols:
        out.append(run_one(
            sym,
            fee_mults=tuple(args.fee_mults),
            funding_mults=tuple(args.funding_mults),
            slippage_mults=tuple(args.slippage_mults),
            real_funding=args.real_funding,
        ))
    payload = {
        "report": "cost_sensitivity_envelope",
        "fee_mults": list(args.fee_mults),
        "funding_mults": list(args.funding_mults),
        "slippage_mults": list(args.slippage_mults),
        "symbols": out,
        "selection_blocked": all(s["selection_blocked"] for s in out),
        "promotion_blocked": all(s["promotion_blocked"] for s in out),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
