"""Independent monitor-tick watchdog for the autonomous runtime.

Review P1-2: the fail-closed breakers (``heartbeat``, ``resource``) are only tripped
by injected tests today. ``AutonomousPaperRuntime.process`` beats + ticks the monitors,
but ``process`` only runs when a snapshot arrives. When cycles *stop* arriving, nothing
ticks the monitors, so a stalled runtime never trips the heartbeat breaker in production
and the breaker is decorative.

This watchdog is the independent timer a daemon loop drives. It calls a ``tick``
callable (wired to ``AutonomousPaperRuntime.tick_monitors`` / ``CanonicalOfflineRuntime
.tick_monitors``) on a fixed cadence, regardless of whether snapshots arrive. With no
cycles for longer than ``max_gap_ms``, the heartbeat monitor trips the breaker and new
entries are parked fail-closed.

No signed calls, no credentials, no orders. Pure offline host + liveness observation.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, cast

from src.policy.breakers import BreakerRegistry


class MonitorWatchdog:
    """Drive a monitor ``tick`` callable on a fixed interval, independent of cycles.

    ``tick`` is typically ``runtime.tick_monitors`` (which evaluates the attached
    ``HeartbeatMonitor`` and ``ResourceMonitor`` and trips/clear the breaker registry).
    The watchdog calls it every ``interval_seconds``; a stall (no fresh heartbeat beat)
    is therefore detected by the heartbeat monitor even when no snapshot is being
    processed.
    """

    def __init__(
        self,
        tick: Callable[[], None],
        *,
        interval_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not callable(tick):
            raise TypeError("tick must be callable")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._tick = tick
        self.interval_seconds = float(interval_seconds)
        self._clock = clock
        self._sleep = sleep
        self.running = False
        self._last_tick: float | None = None
        self.tick_count = 0

    def _due(self, now: float) -> bool:
        return self._last_tick is None or (now - self._last_tick) >= self.interval_seconds

    def tick_once(self, now: float | None = None) -> None:
        """Invoke the monitor tick once and record the time (used by ``run`` and tests)."""
        self._tick()
        self._last_tick = now if now is not None else self._clock()
        self.tick_count += 1

    async def run(self, poll_seconds: float = 0.05) -> None:
        """Loop: call ``tick`` on cadence until ``stop``. Drives the monitor trip live."""
        self.running = True
        try:
            while self.running:
                now = self._clock()
                if self._due(now):
                    self.tick_once(now)
                await self._sleep(poll_seconds)
        finally:
            self.running = False

    def stop(self) -> None:
        self.running = False


def wire_watchdog_to_runtime(
    runtime: object,
    breakers: BreakerRegistry,
    *,
    interval_seconds: float = 1.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> MonitorWatchdog:
    """Build a watchdog that drives ``runtime.tick_monitors`` on a timer.

    Helper for harnesses (scripts / daemon loops) so the monitor trip is driven live
    rather than by injected tests. ``runtime`` must expose a ``tick_monitors`` callable.
    """
    tick = getattr(runtime, "tick_monitors")
    if not callable(tick):
        raise TypeError("runtime must expose a callable tick_monitors()")
    monitor_tick = cast(Callable[[], None], tick)
    return MonitorWatchdog(monitor_tick, interval_seconds=interval_seconds, clock=clock, sleep=sleep)
