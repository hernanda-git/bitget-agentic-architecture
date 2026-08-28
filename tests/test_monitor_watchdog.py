"""Phase 39 — Monitor watchdog: drive Heartbeat/Resource monitors on a timer.

Review P1-2: the fail-closed breakers (heartbeat, resource) are only tripped by
injected tests today. Nothing in the standing scaffold ticks them on a timer, so a
stalled runtime (cycles stop arriving) never trips the heartbeat breaker in
production. This module is the independent watchdog that a daemon loop drives; it
calls the runtime's ``tick_monitors`` on a cadence regardless of whether snapshots
arrive, so a stall is detected and entries are parked fail-closed.

RED first: ``src.runtime.monitor_watchdog.MonitorWatchdog`` does not exist yet, so
these tests fail to import (feature missing, not a typo).
"""
from __future__ import annotations

import asyncio

import pytest

from src.runtime.monitor_watchdog import MonitorWatchdog


def test_watchdog_rejects_non_positive_interval():
    with pytest.raises(ValueError):
        MonitorWatchdog(lambda: None, interval_seconds=0.0)
    with pytest.raises(ValueError):
        MonitorWatchdog(lambda: None, interval_seconds=-1.0)


def test_watchdog_rejects_non_callable_tick():
    with pytest.raises(TypeError):
        MonitorWatchdog(None)  # type: ignore[arg-type]


def test_watchdog_ticks_on_due_cadence():
    calls: list[float] = []
    clk = {"t": 0.0}

    wd = MonitorWatchdog(lambda: calls.append(clk["t"]), interval_seconds=1.0, clock=lambda: clk["t"])
    # Cold start: no last tick -> immediately due and ticks.
    wd.tick_once(0.0)
    assert len(calls) == 1
    # Half the interval later: not yet due.
    clk["t"] = 0.5
    assert not wd._due(0.5)
    # At the interval boundary: due.
    clk["t"] = 1.0
    assert wd._due(1.0)
    wd.tick_once(1.0)
    assert len(calls) == 2


def test_watchdog_run_loop_drives_tick_on_schedule():
    calls: list[float] = []
    clk = {"t": 0.0}

    async def fake_sleep(dt: float) -> None:
        clk["t"] += dt
        # Must actually yield to the event loop or the run loop busy-loops.
        await asyncio.sleep(0)

    wd = MonitorWatchdog(
        lambda: calls.append(clk["t"]),
        interval_seconds=1.0,
        clock=lambda: clk["t"],
        sleep=fake_sleep,
    )

    async def drive() -> None:
        task = asyncio.create_task(wd.run(poll_seconds=0.05))
        # Let the loop run for a moment of real time; fake_sleep advances the
        # simulated clock by interval_seconds each poll, producing several ticks.
        await asyncio.sleep(0.5)
        wd.stop()
        await task

    asyncio.run(drive())
    # Simulated time advances far past the 1s interval -> multiple ticks fired.
    assert len(calls) >= 3, calls


def test_watchdog_stop_ends_loop():
    calls: list[int] = []
    wd = MonitorWatchdog(lambda: calls.append(1), interval_seconds=0.01, sleep=asyncio.sleep)

    async def drive() -> None:
        task = asyncio.create_task(wd.run(poll_seconds=0.005))
        await asyncio.sleep(0.1)
        wd.stop()
        await task

    asyncio.run(drive())
    assert wd.running is False
    assert len(calls) >= 1
