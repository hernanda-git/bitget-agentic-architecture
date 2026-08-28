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
from src.market.models import MarketSnapshot
from src.agent.context import PortfolioView
from src.runtime.canonical import CanonicalOfflineRuntime
from src.runtime.heartbeat import HeartbeatMonitor
from src.runtime.resource_monitor import ResourceMonitor
from src.policy.breakers import BreakerRegistry, BreakerStore
from src.reporting import write_run_report


def run_shadow(cycles: int, symbols: list[str], ledger_path: Path, reports_dir: Path,
              run_id: str | None = None, reset: bool = False, monitor: bool = True) -> dict:
    if cycles < 1 or not symbols:
        raise ValueError("cycles and symbols must be non-empty")
    ledger = EventLedger(ledger_path, run_id=run_id)
    if reset:
        ledger.reset()
    # Fail-closed live monitors (opt-out via monitor=False): attached to a shared
    # breaker registry so a stalled or resource-degraded runtime parks new entries.
    breakers = BreakerRegistry(BreakerStore(ledger_path.with_suffix(ledger_path.suffix + ".breakers.json")))
    hb = HeartbeatMonitor(max_gap_ms=max(60_000, cycles * 2_000)) if monitor else None
    rm = ResourceMonitor() if monitor else None
    if hb is not None:
        hb.attach(breakers)
    if rm is not None:
        rm.attach(breakers)
    runtime = CanonicalOfflineRuntime.fixture_shadow(ledger, heartbeat=hb, resource_monitor=rm)
    for cycle in range(cycles):
        for symbol in symbols:
            snapshot = MarketSnapshot(symbol, 100, 99.99, 100.01, 0, 1,
                                      int(time.time() * 1000) + cycle, int(time.time() * 1000) + cycle).with_hash()
            import asyncio
            asyncio.run(runtime.process(snapshot, PortfolioView(), snapshot.observed_ts_ms))
            runtime.tick_monitors()
    events = ledger.all()
    counts = Counter(event["event_type"] for event in events)
    report = {"run_id": uuid.uuid4().hex[:12], "mode": "shadow", "source": "fixture-shadow", "status": "SHADOW_ONLY",
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
    parser.add_argument("--run-id", default=None, help="tag this run so ledger PnL is scoped, not blended with prior runs")
    parser.add_argument("--reset", action="store_true", help="delete all prior ledger rows before this run")
    parser.add_argument("--no-monitor", action="store_true", help="disable the heartbeat/resource live monitors (not recommended)")
    args = parser.parse_args()
    if args.signed:
        parser.error("signed execution is not implemented; shadow mode is observation-only")
    try:
        report = run_shadow(args.cycles, [s.strip().upper() for s in args.symbols.split(",") if s.strip()],
                            Path(args.ledger), Path(args.reports_dir), run_id=args.run_id, reset=args.reset,
                            monitor=not args.no_monitor)
    except Exception as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
