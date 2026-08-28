"""P1: HeartbeatMonitor / ResourceMonitor must actually be ticked by the runtime.

RED first: before wiring, nothing in src/ instantiates or ticks these monitors,
so a stalled or resource-degraded runtime never parks entries (decorative).
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.market.models import MarketSnapshot
from src.policy.breakers import BreakerRegistry, BreakerStore
from src.providers.fake import FakeProvider
from src.agent.context import PortfolioView
from src.agentic_engine import Policy
from src.runtime.canonical import CanonicalOfflineRuntime
from src.runtime.heartbeat import HeartbeatMonitor
from src.runtime.resource_monitor import ResourceMonitor


def _runtime_with_monitors(max_gap_ms=1000, clock=None, resource_policy=None):
    import itertools
    ledger = EventLedger(Path(tempfile.mktemp(suffix=".sqlite3")))
    breakers = BreakerRegistry(BreakerStore(Path(tempfile.mktemp(suffix=".json"))))
    hb = HeartbeatMonitor(max_gap_ms=max_gap_ms, clock=clock)
    rm = ResourceMonitor(policy=resource_policy, clock=clock)
    hb.attach(breakers)
    rm.attach(breakers)
    policy = Policy(frozenset(["BTCUSDT"]), 3, 1_000, 50, 10, kill_switch=False)
    # itertools.repeat gives every cycle a fresh decision (FakeProvider is finite).
    provider = FakeProvider(itertools.repeat(_resp("BTCUSDT", 100)))
    rt = CanonicalOfflineRuntime.paper(
        provider, policy, ledger, FakeExchange(),
        breakers=breakers, heartbeat=hb, resource_monitor=rm,
    )
    return rt, breakers, hb, rm


def _resp(symbol, price):
    import json
    body = {"decision_id": "offline-enter-001", "action": "ENTER", "symbol": symbol, "side": "BUY",
            "entry": price, "stop_loss": price * 0.95, "take_profit": price * 1.1,
            "leverage": 1, "max_notional_usd": 100, "valid_until_ms": 9_999_999_999_999,
            "thesis": "t", "invalidation": "i"}
    from src.providers.ports import ProviderResponse
    return ProviderResponse(status="OK", content=json.dumps(body), provider="fake", model="fixture", prompt_version="v1")


def _snap(symbol="BTCUSDT", price=100.0, ts=1_700_000_000_000):
    return MarketSnapshot(symbol, price, price - 0.01, price + 0.01, 0, 1, ts, ts).with_hash()


def test_healthy_cycle_is_not_parked_and_beats(tmp_path):
    rt, breakers, hb, rm = _runtime_with_monitors()
    snap = _snap(ts=1)
    res = asyncio.run(rt.process(snap, PortfolioView(), now_ts_ms=1))
    assert res["status"] in ("EXECUTED", "DEGRADED")
    assert not breakers.entries_parked()
    assert hb.status() == "HEALTHY"


def test_stall_trips_heartbeat_breaker_and_parks_new_entries(tmp_path):
    clk = {"t": 0}
    rt, breakers, hb, rm = _runtime_with_monitors(max_gap_ms=1000, clock=lambda: clk["t"])
    # First cycle beats at t=1000.
    asyncio.run(rt.process(_snap(ts=1000), PortfolioView(), now_ts_ms=1000))
    assert hb.status() == "HEALTHY"
    # No cycle for >max_gap: the live monitor loop ticks and trips the breaker.
    clk["t"] = 5000
    rt.tick_monitors()
    assert breakers.is_open("heartbeat")
    assert breakers.entries_parked()
    # During the stall the breaker is open -> a PARKED entry would be produced
    # (fail-closed). The model cannot clear it; only a verified fresh beat can.
    res = asyncio.run(rt.process(_snap(ts=5000), PortfolioView(), now_ts_ms=5000))
    # A fresh cycle auto-recovers (verified automatic recovery): liveness observed
    # again, so the entry is no longer parked by heartbeat. This proves the
    # monitor is wired end-to-end (trip on stall, recover on fresh beat).
    assert res["status"] in ("EXECUTED", "DEGRADED")
    assert not breakers.is_open("heartbeat")


def test_resource_degradation_parks_entries(tmp_path):
    from scripts.resource_guard import GuardPolicy
    # Force a guaranteed violation: impossible min memory so every sample is DEGRADED.
    policy = GuardPolicy(min_available_memory_mb=10**12)
    rt, breakers, hb, rm = _runtime_with_monitors(resource_policy=policy)
    rt.tick_monitors()
    assert breakers.is_open("resource")
    assert breakers.entries_parked()
    # A cycle arriving while the resource breaker is open is parked fail-closed
    # (the model cannot clear it).
    res = asyncio.run(rt.process(_snap(ts=1_700_000_000_000), PortfolioView(), now_ts_ms=1_700_000_000_000))
    assert res["status"] == "PARKED"
    assert res["reason"] == "BREAKER_OPEN"
