"""Bounded event scheduler for one active paper cycle per symbol."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Callable


class PaperScheduler:
    def __init__(self, runtime: Any, *, min_interval_seconds: float = 1.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.runtime = runtime
        self.min_interval_seconds = max(float(min_interval_seconds), 0.0)
        self.clock = clock
        self._queue: deque[Any] = deque()
        self._queued: set[tuple[str, str]] = set()
        self._active: set[str] = set()
        self._last_run: dict[str, float] = {}
        self.parked: dict[str, str] = {}
        self.running = True
        self._lock = asyncio.Lock()

    def enqueue(self, snapshot: Any) -> bool:
        key = (snapshot.symbol, self._digest(snapshot))
        if key in self._queued or snapshot.symbol in self._active:
            return False
        self._queue.append(snapshot)
        self._queued.add(key)
        return True

    async def run_once(self, portfolio: Any = None, now_ts_ms: int | None = None) -> int:
        async with self._lock:
            if not self._queue or not self.running:
                return 0
            snapshot = self._queue.popleft()
            self._queued.discard((snapshot.symbol, self._digest(snapshot)))
            if snapshot.symbol in self._active:
                self.enqueue(snapshot)
                return 0
            last = self._last_run.get(snapshot.symbol)
            if last is not None and self.clock() - last < self.min_interval_seconds:
                self.enqueue(snapshot)
                return 0
            self._active.add(snapshot.symbol)
        try:
            result = await self.runtime.process(snapshot, portfolio, now_ts_ms)
            status = str(result.get("status", ""))
            if status in {"PARKED_PROVIDER", "PARKED", "PARKED_KILL_SWITCH", "PARKED_RECONCILIATION", "PARKED_RISK"}:
                self.parked[snapshot.symbol] = status
            self._last_run[snapshot.symbol] = self.clock()
            return 1
        finally:
            self._active.discard(snapshot.symbol)

    async def run(self, *, poll_seconds: float = 0.05) -> None:
        self.running = True
        while self.running:
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(poll_seconds)

    def stop(self) -> None:
        self.running = False
        self._queue.clear()
        self._queued.clear()

    @staticmethod
    def _digest(snapshot: Any) -> str:
        return str(getattr(snapshot, "snapshot_hash", "") or getattr(snapshot, "computed_hash")())
