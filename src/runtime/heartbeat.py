"""Runtime heartbeat / stall monitor for daemon liveness.

A daemon can emit perfectly-formed, perfectly-constant payloads forever and pass
every health check while computing nothing (build-verification skill: verify the
OUTPUT VARIES, not that the service is up). This monitor detects *liveness
regression*: if the autonomous runtime stops producing cycles for longer than
``max_gap_ms``, it is STALLED and must park new entries fail-closed via the
``heartbeat`` breaker. A fresh heartbeat is a verified automatic recovery that
clears the monitor's own trip.

Design guarantees:
* No signed calls, no credentials, no orders. Pure offline measurement.
* Cold start is UNKNOWN, never STALLED: a fresh runtime is not parked before its
  first cycle.
* STALLED always implies ``should_park()`` is True (fail-closed).
* The model can never clear the breaker; only an operator or a verified automatic
  recovery (fresh heartbeat) may clear it.
* The monitor only auto-clears trips it itself raised. An operator-initiated trip
  is preserved until the operator clears it.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from src.policy.breakers import BreakerRegistry

DEFAULT_CLOCK: Callable[[], int] = lambda: int(time.monotonic() * 1000)


class HeartbeatMonitor:
    def __init__(
        self,
        max_gap_ms: int,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if max_gap_ms <= 0:
            raise ValueError("max_gap_ms must be positive")
        self.max_gap_ms = max_gap_ms
        self._clock = clock or DEFAULT_CLOCK
        self._last_beat_ms: Optional[int] = None
        self._registry: Optional[BreakerRegistry] = None
        self._tripped_by_monitor = False

    def attach(self, registry: BreakerRegistry) -> None:
        """Wire the monitor to a breaker registry so stalls can park entries."""
        self._registry = registry

    def beat(self, now_ms: int | None = None) -> None:
        """Record a heartbeat (a completed cycle). Recovers own trips on fresh beat."""
        now = now_ms if now_ms is not None else self._clock()
        if self._last_beat_ms is not None and now < self._last_beat_ms:
            raise ValueError("heartbeat timestamp regressed")
        self._last_beat_ms = now
        # Verified automatic recovery: a fresh beat clears a monitor-raised trip.
        if (
            self._registry is not None
            and self._tripped_by_monitor
            and self._registry.is_open("heartbeat")
        ):
            self._registry.clear("heartbeat", actor="auto_recovery")
            self._tripped_by_monitor = False

    def status(self, now_ms: int | None = None) -> str:
        """Return ``UNKNOWN`` (cold start), ``HEALTHY``, or ``STALLED``."""
        if self._last_beat_ms is None:
            return "UNKNOWN"
        now = now_ms if now_ms is not None else self._clock()
        # Fail-closed boundary: the gap must exceed the limit before we declare
        # a stall. Exactly at the limit (gap == max_gap_ms) is still healthy.
        return "STALLED" if (now - self._last_beat_ms) > self.max_gap_ms else "HEALTHY"

    def is_stalled(self, now_ms: int | None = None) -> bool:
        return self.status(now_ms) == "STALLED"

    def should_park(self, now_ms: int | None = None) -> bool:
        """Fail-closed: a stall must park new entries."""
        return self.is_stalled(now_ms)

    def tick(self, now_ms: int | None = None) -> str:
        """Integration step: evaluate liveness and trip/clear the breaker.

        Returns the current status. On stall it trips the ``heartbeat`` breaker
        (parking entries). When healthy again it clears a trip *it* raised.
        """
        now = now_ms if now_ms is not None else self._clock()
        st = self.status(now)
        if st == "STALLED" and self._registry is not None:
            if not self._registry.is_open("heartbeat"):
                gap = now - self._last_beat_ms if self._last_beat_ms is not None else now
                self._registry.trip(
                    "heartbeat",
                    f"no heartbeat for {gap}ms (max {self.max_gap_ms}ms)",
                )
                self._tripped_by_monitor = True
        elif st == "HEALTHY" and self._registry is not None and self._tripped_by_monitor:
            if self._registry.is_open("heartbeat"):
                self._registry.clear("heartbeat", actor="auto_recovery")
            self._tripped_by_monitor = False
        return st
