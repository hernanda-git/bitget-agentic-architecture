"""Bounded public-observation shadow runner. It never calls signed endpoints."""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ledger.sqlite import EventLedger
from src.reporting import write_run_report


def run_shadow(cycles: int, symbols: list[str], ledger_path: Path, reports_dir: Path) -> dict:
    if cycles < 1 or not symbols:
        raise ValueError("cycles and symbols must be non-empty")
    ledger = EventLedger(ledger_path)
    for cycle in range(cycles):
        for symbol in symbols:
            ledger.append("SHADOW_TICK_OBSERVED", {"cycle": cycle, "symbol": symbol, "source": "fixture_public"})
    events = ledger.all()
    counts = Counter(event["event_type"] for event in events)
    report = {"run_id": uuid.uuid4().hex[:12], "mode": "shadow", "status": "SHADOW_ONLY",
              "integrity_ok": True, "cycles_requested": cycles, "cycles_completed": cycles,
              "orders_placed": 0, "signed_calls": 0, "network_calls": 0,
              "counts": {**counts, "cycles": cycles}, "rejection_codes": {},
              "degraded_states": [], "duplicate_prevention": {"duplicate_events": 0},
              "protection_reconciliation": {"status": "not_applicable"},
              "provider": {"name": "none", "calls": 0, "failures": 0, "latency_ms": 0},
              "fee_inclusive_outcome": {"fees_paid": 0.0, "realized_pnl": 0.0},
              "anomalies": [], "observed_symbols": symbols, "created_ms": int(time.time() * 1000)}
    write_run_report(report, reports_dir)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="bounded shadow mode with fixture public observations only")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--symbols", default="BTCUSDT")
    parser.add_argument("--ledger", default="data/autonomous-shadow.sqlite3")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--signed", action="store_true", help="rejected: signed execution is not implemented")
    args = parser.parse_args()
    if args.signed:
        parser.error("signed execution is not implemented; shadow mode is observation-only")
    try:
        report = run_shadow(args.cycles, [s.strip().upper() for s in args.symbols.split(",") if s.strip()],
                            Path(args.ledger), Path(args.reports_dir))
    except Exception as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
