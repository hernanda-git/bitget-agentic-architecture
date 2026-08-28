"""Phase 39 — PaperScheduler drives the monitor tick on a timer (P1-2 closure).

The previous wiring (``AutonomousPaperRuntime.process`` beats + ticks monitors) only
runs when a snapshot arrives. When cycles STOP, nothing ticks the monitors, so the
heartbeat breaker is never tripped live. This test proves the *scheduler* now owns an
independent monitor-tick step that trips the heartbeat breaker on a stall, going
through the scheduler only (never a manual ``runtime.tick_monitors()`` call).

RED first: ``PaperScheduler`` does not accept ``monitor_tick`` / ``monitor_interval_seconds``
and has no ``tick_monitors_now``; ``CanonicalOfflineRuntime.paper`` does not build a
``MonitorWatchdog``. Those attribute/param errors are genuine missing-feature failures.
"""
from __future__ import annotations

import asyncio
import itertools
import tempfile
from pathlib import Path

from src.agent.context import PortfolioView
from src.agentic_engine import Policy
from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.market.models import MarketSnapshot
from src.policy.breakers import BreakerRegistry, BreakerStore
from src.providers.fake import FakeProvider
from src.runtime.heartbeat import HeartbeatMonitor
from src.runtime.paper_runtime import AutonomousPaperRuntime
from src.runtime.resource_monitor import ResourceMonitor
from src.runtime.scheduler import PaperScheduler


def _resp(symbol: str, price: float):
    import json
    from src.providers.ports import ProviderResponse

    body = {"decision_id": "offline-enter-001", "action": "ENTER", "symbol": symbol, "side": "BUY",
            "entry": price, "stop_loss": price * 0.95, "take_profit": price * 1.1,
            "leverage": 1, "max_notional_usd": 100, "valid_until_ms": 9_999_999_999_999,
            "thesis": "t", "invalidation": "i"}
    return ProviderResponse(status="OK", content=json.dumps(body), provider="fake", model="fixture", prompt_version="v1")


def _snap(symbol: str = "BTCUSDT", price: float = 100.0, ts: int = 1) -> MarketSnapshot:
    return MarketSnapshot(symbol, price, price - 0.01, price + 0.01, 0, 1, ts, ts).with_hash()


def _runtime_with_monitors(max_gap_ms: int = 1000, clock=None):
    ledger = EventLedger(Path(tempfile.mktemp(suffix=".sqlite3")))
    breakers = BreakerRegistry(BreakerStore(Path(tempfile.mktemp(suffix=".json"))))
    hb = HeartbeatMonitor(max_gap_ms=max_gap_ms, clock=clock)
    rm = ResourceMonitor(policy=None, clock=clock)
    hb.attach(breakers)
    rm.attach(breakers)
    policy = Policy(frozenset(["BTCUSDT"]), 3, 1000, 50, 10, kill_switch=False)
    provider = FakeProvider(itertools.repeat(_resp("BTCUSDT", 100)))
    rt = AutonomousPaperRuntime(
        provider, policy, ledger, FakeExchange(),
        breakers=breakers, heartbeat=hb, resource_monitor=rm,
    )
    return rt, breakers, hb, rm


def test_scheduler_watchdog_step_trips_heartbeat_breaker_on_stall():
    clk = {"t": 1_700_000_000_000}
    rt, breakers, hb, rm = _runtime_with_monitors(max_gap_ms=1000, clock=lambda: clk["t"])
    # Scheduler is wired to the runtime's monitor tick (what a running loop drives).
    sched = PaperScheduler(
        rt, clock=lambda: clk["t"],
        monitor_tick=rt.tick_monitors, monitor_interval_seconds=0.5,
    )
    # One healthy cycle beats the heartbeat at t=NOW.
    sched.enqueue(_snap(ts=clk["t"]))
    assert asyncio.run(sched.run_once(portfolio=PortfolioView(), now_ts_ms=clk["t"])) == 1
    assert hb.status() == "HEALTHY"
    # Cycles stop arriving. The scheduler's watchdog step (driven on a timer in
    # production) evaluates the monitors as time passes. No manual rt.tick_monitors().
    clk["t"] = 1_700_000_001_500
    sched.tick_monitors_now()
    # The watchdog-driven tick must open the heartbeat breaker fail-closed.
    assert breakers.is_open("heartbeat"), "watchdog-driven monitor tick must trip on stall"
    assert breakers.entries_parked()


def test_scheduler_run_ticks_monitor_on_schedule_real_time():
    rt, breakers, hb, rm = _runtime_with_monitors()
    calls: list[int] = []
    sched = PaperScheduler(
        rt, monitor_tick=lambda: calls.append(1), monitor_interval_seconds=0.05, min_interval_seconds=0.0,
    )

    async def drive() -> None:
        task = asyncio.create_task(sched.run(poll_seconds=0.01))
        await asyncio.sleep(0.3)
        sched.stop()
        await task

    asyncio.run(drive())
    # ~0.3s of wall time at a 0.05s interval -> the run loop called monitor_tick.
    assert len(calls) >= 3, calls


def test_canonical_start_monitor_loop_runs_watchdog():
    """The canonical wrapper must actually start a ticking watchdog loop (P1-2 closure).

    RED-by-design guard against a wiring-disabled wrapper: if ``start_monitor_loop``
    returns a no-op task (the exact mutation-artifact class of bug that broke
    ``PaperScheduler.tick_monitors_now`` in a prior session), the watchdog never ticks
    and this assertion fails.
    """
    from src.runtime.canonical import CanonicalOfflineRuntime

    ledger = EventLedger(Path(tempfile.mktemp(suffix=".sqlite3")))
    breakers = BreakerRegistry(BreakerStore(Path(tempfile.mktemp(suffix=".json"))))
    hb = HeartbeatMonitor(max_gap_ms=1000)
    rm = ResourceMonitor(policy=None)
    hb.attach(breakers)
    rm.attach(breakers)
    policy = Policy(frozenset(["BTCUSDT"]), 3, 1000, 50, 10, kill_switch=False)
    provider = FakeProvider(itertools.repeat(_resp("BTCUSDT", 100)))
    canon = CanonicalOfflineRuntime.paper(
        provider, policy, ledger, FakeExchange(),
        breakers=breakers, heartbeat=hb, resource_monitor=rm,
        monitor_interval_seconds=0.05,
    )

    async def drive() -> int:
        task = canon.start_monitor_loop()
        try:
            await asyncio.sleep(0.3)
        finally:
            task.cancel()
        return canon.monitor_watchdog.tick_count

    ticks = asyncio.run(drive())
    # ~0.3s of wall time at a 0.05s interval -> the started loop drove the watchdog.
    assert ticks >= 3, ticks


def test_canonical_paper_builds_monitor_watchdog():
    from src.runtime.canonical import CanonicalOfflineRuntime
    from src.runtime.monitor_watchdog import MonitorWatchdog

    clk = {"t": 1_700_000_000_000}
    ledger = EventLedger(Path(tempfile.mktemp(suffix=".sqlite3")))
    breakers = BreakerRegistry(BreakerStore(Path(tempfile.mktemp(suffix=".json"))))
    hb = HeartbeatMonitor(max_gap_ms=1000, clock=lambda: clk["t"])
    rm = ResourceMonitor(policy=None, clock=lambda: clk["t"])
    hb.attach(breakers)
    rm.attach(breakers)
    policy = Policy(frozenset(["BTCUSDT"]), 3, 1000, 50, 10, kill_switch=False)
    provider = FakeProvider(itertools.repeat(_resp("BTCUSDT", 100)))
    canon = CanonicalOfflineRuntime.paper(
        provider, policy, ledger, FakeExchange(),
        breakers=breakers, heartbeat=hb, resource_monitor=rm,
        monitor_interval_seconds=0.5,
    )
    # The canonical scaffold now owns a watchdog that drives tick_monitors on a timer.
    assert isinstance(canon.monitor_watchdog, MonitorWatchdog)
    # A real cycle completes and beats the heartbeat at t=NOW.
    res = asyncio.run(canon.process(_snap(ts=clk["t"]), PortfolioView(), now_ts_ms=clk["t"]))
    assert res["status"] in ("EXECUTED", "DEGRADED")
    assert hb.status() == "HEALTHY"
    # Cycles stop arriving. The watchdog is the only thing ticking the monitors.
    clk["t"] = 1_700_000_001_500
    canon.monitor_watchdog.tick_once(1_700_000_001_500)
    # Without any new cycle, the watchdog-driven tick must trip the heartbeat breaker.
    assert breakers.is_open("heartbeat")
