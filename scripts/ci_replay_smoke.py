"""Integration replay smoke for the canonical offline runtime.

Drives the REAL composition root (CanonicalOfflineRuntime) with FAKE adapters
through ~120 real-shaped snapshots and asserts zero crashes plus a
non-degenerate decision mix.

This is a verification gate (build-verification skill), not a feature: the
orchestrator/composition root already exists. It proves the wiring actually
launches and routes a varied message stream end to end.

Entirely offline: no network, no signed calls, no live exchange. Each snapshot
gets a fresh FakeExchange + provider instance so open-position state does not
bleed across cycles, while a single shared EventLedger records every event.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.context import PortfolioView
from src.agentic_engine import Policy
from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.market.models import MarketSnapshot
from src.providers.fake import FakeProvider
from src.providers.ports import ProviderResponse
from src.runtime.canonical import CanonicalOfflineRuntime

N = 120


def _decision(i: int) -> ProviderResponse:
    now = int(time.time() * 1000)
    if i % 7 == 0:
        body = {"decision_id": f"smoke-decision-{i:03d}", "action": "HOLD", "symbol": "BTCUSDT",
                "side": "NONE", "entry": None, "stop_loss": None, "take_profit": None,
                "leverage": 1, "max_notional_usd": 10, "valid_until_ms": now + 60_000,
                "thesis": "smoke", "invalidation": "x"}
    elif i % 11 == 0:
        # Disallowed symbol -> REJECTED (SYMBOL_NOT_ALLOWED / MARKET_SYMBOL_MISMATCH)
        body = {"decision_id": f"smoke-decision-{i:03d}", "action": "ENTER", "symbol": "SOLUSDT",
                "side": "BUY", "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
                "leverage": 1, "max_notional_usd": 10, "valid_until_ms": now + 60_000,
                "thesis": "smoke", "invalidation": "x"}
    else:
        sym = "BTCUSDT" if i % 2 == 0 else "ETHUSDT"
        body = {"decision_id": f"smoke-decision-{i:03d}", "action": "ENTER", "symbol": sym,
                "side": "BUY", "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
                "leverage": 1, "max_notional_usd": 10, "valid_until_ms": now + 60_000,
                "thesis": "smoke", "invalidation": "x"}
    return ProviderResponse("OK", json.dumps(body))


def _snapshot(i: int, *, stale: bool = False) -> MarketSnapshot:
    now = int(time.time() * 1000)
    observed = now - (10_000_000 if stale else i * 100)
    return MarketSnapshot("BTCUSDT", 100.0, 99.99, 100.01, 0.0002, 1,
                          observed, now - i * 100).with_hash()


def run_smoke(ledger_path: Path) -> dict:
    ledger = EventLedger(ledger_path)
    policy = Policy(frozenset({"BTCUSDT", "ETHUSDT"}), max_leverage=3,
                    max_position_notional_usd=25, max_spread_bps=30,
                    max_snapshot_age_seconds=7200, kill_switch=False)
    statuses: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    orders = 0
    crashes = 0
    for i in range(N):
        stale = (i % 13 == 0)
        provider = FakeProvider([_decision(i)])
        runtime = CanonicalOfflineRuntime.paper(
            provider, policy, ledger, FakeExchange())
        try:
            result = asyncio.run(runtime.process(_snapshot(i, stale=stale),
                                                 PortfolioView(), int(time.time() * 1000)))
        except Exception as exc:  # pragma: no cover - defensive for the smoke itself
            crashes += 1
            statuses["CRASH"] += 1
            reasons[f"CRASH:{type(exc).__name__}"] += 1
            continue
        statuses[result.get("status", "UNKNOWN")] += 1
        if result.get("reason"):
            reasons[result["reason"]] += 1
    events = ledger.all()
    # Orders are recorded as ORDER_SUBMITTED ledger events by the paper runtime;
    # the per-cycle result dict does not echo a count, so derive it from the
    # durable ledger (the source of truth for reconciliation).
    orders = sum(1 for e in events if e["event_type"] == "ORDER_SUBMITTED")
    terminals = [e for e in events if e["event_type"] == "CYCLE_TERMINAL"]
    return {
        "messages": N,
        "crashes": crashes,
        "statuses": dict(statuses),
        "reasons": dict(reasons),
        "orders_placed": orders,
        "terminal_events": len(terminals),
        "distinct_statuses": len([s for s in statuses if s != "CRASH"]),
        "ledger_events": len(events),
    }


def main() -> int:
    import tempfile
    fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    fd.close()
    result = run_smoke(Path(fd.name))
    required = {"EXECUTED", "HELD", "REJECTED", "PARKED"}
    missing = required - set(result["statuses"])
    ok = (result["crashes"] == 0 and result["terminal_events"] == N
          and result["orders_placed"] > 0 and not missing)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not ok:
        print(f"SMOKE FAIL: crashes={result['crashes']} "
              f"terminals={result['terminal_events']}/{N} "
              f"orders={result['orders_placed']} missing={sorted(missing)}")
        return 1
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
