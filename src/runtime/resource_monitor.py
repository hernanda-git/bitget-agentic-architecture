"""Runtime host-resource pressure monitor (fail-closed entry parking).

Host resource pressure (low memory, swap, disk, inode) is observed via
``scripts.resource_guard`` and, when a violation is present, trips the
``resource`` breaker in the ``BreakerRegistry``, parking new entries
fail-closed. When the violation clears, a monitor-raised trip is cleared via
verified auto-recovery. The model can never clear the breaker.

No signed calls, no credentials, no orders. Pure offline host observation.

Design mirrors ``src.runtime.heartbeat``:
* Cold start is ``UNKNOWN``, never ``DEGRADED``: a fresh runtime is not parked
  before its first sample.
* ``DEGRADED`` always implies ``should_park()`` is True (fail-closed).
* The model can never clear the breaker; only an operator or a verified
  automatic recovery (a clean sample) may clear a trip the monitor raised.
* A sample observation error is treated fail-closed as ``DEGRADED`` (we must
  not assume the host is healthy when we cannot measure it).
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from scripts.resource_guard import GuardPolicy, ResourceSnapshot, snapshot, violations

from src.policy.breakers import BreakerRegistry

BREAKER_NAME = "resource"
DEFAULT_CLOCK: Callable[[], int] = lambda: int(time.monotonic() * 1000)


class ResourceMonitor:
    def __init__(
        self,
        policy: GuardPolicy | None = None,
        snapshot_source: Callable[[], ResourceSnapshot] = snapshot,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.policy = policy or GuardPolicy()
        self._snapshot_source = snapshot_source
        self._clock = clock or DEFAULT_CLOCK
        self._registry: Optional[BreakerRegistry] = None
        self._tripped_by_monitor = False
        self._sampled = False
        self._violations: list[str] = []
        self._last_sample: Optional[ResourceSnapshot] = None

    def attach(self, registry: BreakerRegistry) -> None:
        """Wire the monitor to a breaker registry so pressure can park entries."""
        self._registry = registry

    def sample(self, now_ms: int | None = None) -> Optional[ResourceSnapshot]:
        """Observe host resources; fail closed on observation error."""
        self._sampled = True
        try:
            self._last_sample = self._snapshot_source()
            self._violations = violations(self._last_sample, self.policy)
        except Exception:
            # Fail closed: we cannot prove the host is healthy, so assume pressure.
            self._violations = ["SNAPSHOT_ERROR"]
        return self._last_sample

    @property
    def violations(self) -> list[str]:
        return list(self._violations)

    @property
    def last_sample(self) -> Optional[ResourceSnapshot]:
        return self._last_sample

    def status(self, now_ms: int | None = None) -> str:
        """Return ``UNKNOWN`` (cold start), ``HEALTHY``, or ``DEGRADED``."""
        if not self._sampled:
            return "UNKNOWN"
        return "DEGRADED" if self._violations else "HEALTHY"

    def is_degraded(self, now_ms: int | None = None) -> bool:
        return self.status(now_ms) == "DEGRADED"

    def should_park(self, now_ms: int | None = None) -> bool:
        """Fail-closed: a degraded resource state must park new entries."""
        return self.is_degraded(now_ms)

    def tick(self, now_ms: int | None = None) -> str:
        """Observe once and trip/clear the ``resource`` breaker accordingly.

        Returns the current status. On degradation it trips the ``resource``
        breaker (parking entries). When healthy again it clears a trip *it*
        raised via verified auto-recovery.
        """
        now = now_ms if now_ms is not None else self._clock()
        self.sample(now)
        st = self.status(now)
        if st == "DEGRADED" and self._registry is not None:
            if not self._registry.is_open(BREAKER_NAME):
                self._registry.trip(
                    BREAKER_NAME, f"resource pressure: {', '.join(self._violations)}"
                )
                self._tripped_by_monitor = True
        elif st == "HEALTHY" and self._registry is not None and self._tripped_by_monitor:
            if self._registry.is_open(BREAKER_NAME):
                self._registry.clear(BREAKER_NAME, actor="auto_recovery")
            self._tripped_by_monitor = False
        return st
