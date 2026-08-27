"""Continuous, fail-closed runtime resource budget for autonomous heavy work.

This module only OBSERVES host resource state and raises a catchable
``ResourceBudgetExceeded`` when a budget would be breached. It never restarts or
kills Hermes, deployed bots, databases, or any unrelated service. Use it to wrap
long in-process work (e.g. walk-forward evaluation) so the work aborts itself
before exhausting host memory, swap, disk, or inodes.

It reuses the same snapshot/violation primitives as ``scripts.resource_guard`` so
the preflight and the continuous check share one policy language. The only
difference is that this guard runs INSIDE a long in-process job, not just before
a child process launch.
"""
from __future__ import annotations

import threading
from typing import Callable

from scripts.resource_guard import GuardPolicy, ResourceSnapshot, snapshot, violations


class ResourceBudgetExceeded(Exception):
    """Raised (never a process kill) when the runtime resource budget is breached.

    ``killed_anything`` is always ``False``: the budget only ever raises. The
    caller decides how to degrade (park work, stop the scheduler) -- the budget
    itself never terminates another process.
    """

    def __init__(self, violations, snapshot, budget):
        self.violations = list(violations)
        self.snapshot = snapshot
        self.budget = budget
        self.killed_anything = False
        super().__init__(f"resource budget exceeded: {self.violations}")


class ResourceBudget:
    """Observe host resources and fail closed (raise) before they are exhausted.

    ``snapshot_source`` is injectable for testing; in production it defaults to
    ``scripts.resource_guard.snapshot`` which reads ``/proc/meminfo`` and statvfs.

    Two modes of protection:
      * explicit polling: call ``assert_within()`` between work units (e.g.
        between walk-forward candidates).
      * optional watchdog: a daemon thread samples every ``sample_interval_seconds``
        and records a breach; the next ``assert_within()`` or context exit
        surfaces it. The watchdog never raises inside the thread and never kills.
    """

    def __init__(self, snapshot_source: Callable[[], ResourceSnapshot] = snapshot,
                 policy: GuardPolicy = GuardPolicy(), *,
                 sample_interval_seconds: float = 5.0, watchdog: bool = False):
        if sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds must be positive")
        self._snapshot_source = snapshot_source
        self._policy = policy
        self._interval = float(sample_interval_seconds)
        self._watchdog_enabled = bool(watchdog)
        self._lock = threading.Lock()
        self._breached = False
        self._breach_violations: list[str] = []
        self._breach_snapshot: ResourceSnapshot | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last: ResourceSnapshot | None = None

    @property
    def policy(self) -> GuardPolicy:
        return self._policy

    def sample(self) -> ResourceSnapshot:
        self._last = self._snapshot_source()
        return self._last

    def check_now(self) -> list[str]:
        snap = self.sample()
        return violations(snap, self._policy)

    def preflight(self) -> ResourceSnapshot:
        """Raise before any heavy work starts if the host is already unsafe."""
        snap = self.sample()
        problems = violations(snap, self._policy)
        if problems:
            raise ResourceBudgetExceeded(problems, snap, self)
        return snap

    def assert_within(self) -> None:
        """Raise if the budget is or has been breached. Call between work units."""
        if self._breached:
            with self._lock:
                raise ResourceBudgetExceeded(self._breach_violations,
                                             self._breach_snapshot, self)
        problems = self.check_now()
        if problems:
            with self._lock:
                self._breached = True
                self._breach_violations = problems
                self._breach_snapshot = self._last
            raise ResourceBudgetExceeded(problems, self._last, self)

    # --- optional watchdog -------------------------------------------------

    def start_watchdog(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def stop_watchdog(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=self._interval + 1.0)
        self._thread = None

    def _watch(self) -> None:
        while not self._stop.is_set():
            try:
                problems = self.check_now()
            except Exception:
                problems = ["SNAPSHOT_ERROR"]
            if problems and not self._breached:
                with self._lock:
                    if not self._breached:
                        self._breached = True
                        self._breach_violations = problems
                        self._breach_snapshot = self._last
            # Observe only. The caller surfaces the breach via assert_within()
            # or the context manager exit. Never raise here, never kill.
            self._stop.wait(self._interval)

    @property
    def breached(self) -> bool:
        return self._breached

    @property
    def breach_violations(self) -> list[str]:
        return list(self._breach_violations)

    # --- context manager --------------------------------------------------

    def __enter__(self) -> "ResourceBudget":
        self.preflight()
        if self._watchdog_enabled:
            self.start_watchdog()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._watchdog_enabled:
            self.stop_watchdog()
        if exc_type is None:
            # Final guard before declaring the work clean.
            self.assert_within()
        return False
