"""Real public-data shadow loop. It has no provider, signing, or order path."""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ledger.sqlite import EventLedger
from src.market.bitget_public import BitgetPublicClient
from src.reporting import write_shadow_report


async def run_public_shadow(cycles: int, symbols: list[str], ledger_path: Path, reports_dir: Path,
                            client_factory=None, provider=None) -> dict:
    if cycles < 1 or not symbols:
        raise ValueError("cycles and symbols must be non-empty")
    client_factory = client_factory or (lambda: BitgetPublicClient(venue="bitget", product_type="USDT-FUTURES"))
    client = client_factory()
    if client is None:
        # Unit-test seam: no network is performed, and this is explicitly degraded.
        class NullClient:
            metrics = type("M", (), {"requests": 0, "failures": 0, "schema_rejections": 0, "policy_rejections": 0})()
            async def fetch_snapshot(self, symbol, **kwargs):
                raise RuntimeError("PUBLIC_CLIENT_UNAVAILABLE")
        client = NullClient()
    ledger = EventLedger(ledger_path)
    freshness, spreads, latencies, source_timestamps = [], [], [], []
    completed = 0
    errors = []
    for cycle in range(cycles):
        for symbol in symbols:
            cycle_id = f"public-shadow-{cycle}-{symbol}-{uuid.uuid4().hex[:8]}"
            ledger.claim_cycle(cycle_id, trace_id=cycle_id, mode="public-shadow", product_type="USDT-FUTURES", symbol=symbol)
            started = time.perf_counter()
            try:
                snapshot = await client.fetch_snapshot(symbol, windows=("1m",), limit=100)
                freshness.append(snapshot.freshness_ms)
                source_timestamps.append(snapshot.source_ts_ms)
                spreads.append(snapshot.spread_bps)
                ledger.append("SHADOW_TICK_OBSERVED", {"cycle_id": cycle_id, "trace_id": cycle_id, "mode": "public-shadow",
                    "product_type": "USDT-FUTURES", "symbol": symbol, "source": "bitget-public",
                    "snapshot_hash": snapshot.snapshot_hash, "source_ts_ms": snapshot.source_ts_ms,
                    "observed_ts_ms": snapshot.observed_ts_ms, "disposition": "HOLD"})
                ledger.set_terminal(cycle_id, "HOLD")
                completed += 1
            except Exception as exc:
                errors.append(str(exc))
                ledger.append("SHADOW_TICK_OBSERVED", {"cycle_id": cycle_id, "trace_id": cycle_id, "mode": "public-shadow",
                    "product_type": "USDT-FUTURES", "symbol": symbol, "source": "bitget-public",
                    "disposition": "HOLD", "reason": str(exc)[:120]})
                ledger.set_terminal(cycle_id, "HOLD_DATA_REJECTED")
            latencies.append((time.perf_counter() - started) * 1000)
    metrics = client.metrics
    total = cycles * len(symbols)
    report = {"run_id": uuid.uuid4().hex[:12], "mode": "public-shadow",
              "status": "PUBLIC_SHADOW_COMPLETE" if completed == total else "PUBLIC_SHADOW_DEGRADED",
              "cycles": total, "cycles_requested": cycles, "cycles_completed": completed,
              "provider_calls": 0, "provider_failures": 0,
              "schema_rejections": metrics.schema_rejections, "policy_rejections": metrics.policy_rejections,
              "hold_rate": 1.0, "candidate_rate": 0.0, "simulated_entries": 0, "simulated_exits": 0,
              "net_pnl_after_costs": 0.0, "source_labels": ["bitget-public"],
              "source_timestamp_ms": {"count": len(source_timestamps), "min": min(source_timestamps) if source_timestamps else None,
                                       "max": max(source_timestamps) if source_timestamps else None},
              "freshness_distribution": _distribution(freshness),
              "spread_distribution": _distribution(spreads), "decision_latency": _distribution(latencies),
              "network_calls": metrics.requests, "provider": {"calls": 0, "failures": 0},
              "signed_calls": 0, "orders_placed": 0, "open_positions": 0, "closed_trades": 0,
              "failures": len(errors), "failure_samples": errors[:5],
              "limitations": ["public market observations only", "no provider selection or execution", "PnL is zero because no simulated positions were opened"]}
    write_shadow_report(report, reports_dir)
    return report


def _distribution(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None, "p50": None}
    ordered = sorted(values)
    return {"count": len(values), "min": min(values), "max": max(values),
            "mean": statistics.fmean(values), "p50": ordered[(len(ordered) - 1) // 2]}


def main() -> None:
    parser = argparse.ArgumentParser(description="real unauthenticated Bitget public-data shadow loop")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--symbols", default="BTCUSDT")
    parser.add_argument("--ledger", default="data/public-shadow.sqlite3")
    parser.add_argument("--reports-dir", default="reports/phase-4")
    args = parser.parse_args()
    report = asyncio.run(run_public_shadow(args.cycles, [s.strip().upper() for s in args.symbols.split(",") if s.strip()],
                                           Path(args.ledger), Path(args.reports_dir)))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
