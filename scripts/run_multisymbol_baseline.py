"""Aggregate per-symbol deterministic-baseline reports into one honest report.

This is the unblocked "strengthen walk-forward evaluation + acquire more public
history" deliverable: as the stored evidence base grows (more symbols, deeper
windows), produce a SINGLE honest report that aggregates every per-symbol result
without laundering the blocked baseline into a go-live claim.

It reads the per-symbol reports produced by ``evaluate_real_history.py``
(top-level ``net_pnl`` lives under ``baseline``), extracts the relevant facts,
and delegates to ``src.evaluation.multisymbol.aggregate_symbol_results`` which is
fail-closed: it carries ``selection_blocked=True`` and self-validates with the
recursive ``assert_truthful`` guard.

No network, no credentials, no signed calls, no orders. Reads existing report
files only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation.multisymbol import aggregate_symbol_results

ROOT = Path(__file__).resolve().parents[1]


def _extract_per_symbol(payload: dict) -> dict:
    baseline = payload.get("baseline", {}) or {}
    robustness = payload.get("walk_forward_robustness", {}) or {}
    return {
        "symbol": payload.get("symbol"),
        "product_type": payload.get("product_type"),
        "granularity": payload.get("granularity"),
        "candles": payload.get("candles"),
        "walk_forward_windows": len(payload.get("walk_forward", []) or []),
        "net_pnl": baseline.get("net_pnl"),
        "closed_trades": baseline.get("closed_trades"),
        "promotion_allowed": baseline.get("promotion_allowed"),
        "promotion_reason": baseline.get("promotion_reason"),
        "adequate_sample": bool(robustness.get("adequate_sample", False)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate per-symbol baseline reports into one honest report")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports" / "phase-19",
                        help="directory containing per-symbol *-1m.json reports")
    parser.add_argument("--glob", default="*-1m.json", help="filename pattern for per-symbol reports")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "phase-19" / "aggregate.json")
    args = parser.parse_args()

    files = sorted(args.reports_dir.glob(args.glob))
    if not files:
        print(f"NO_REPORTS_FOUND in {args.reports_dir} ({args.glob})", flush=True)
        return 2

    per_symbol = []
    for f in files:
        try:
            payload = json.loads(f.read_text())
        except Exception as exc:  # noqa: BLE001 - report and skip a malformed file
            print(f"SKIP {f.name}: unreadable ({exc})", flush=True)
            continue
        per_symbol.append(_extract_per_symbol(payload))
        print(f"loaded {f.name}: symbol={per_symbol[-1]['symbol']} "
              f"net_pnl={per_symbol[-1]['net_pnl']} allowed={per_symbol[-1]['promotion_allowed']}",
              flush=True)

    if not per_symbol:
        print("NO_VALID_REPORTS", flush=True)
        return 2

    aggregate = aggregate_symbol_results(per_symbol)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aggregate, indent=2, sort_keys=True, default=str) + "\n")

    print("\n=== MULTI-SYMBOL AGGREGATE ===")
    print(json.dumps({
        "symbols": aggregate["symbols"],
        "overall_net_pnl": aggregate["overall_net_pnl"],
        "overall_closed_trades": aggregate["overall_closed_trades"],
        "selection_blocked": aggregate["selection_blocked"],
        "aggregate_promotion_allowed": aggregate["aggregate_promotion_allowed"],
        "aggregate_promotion_reason": aggregate["aggregate_promotion_reason"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
