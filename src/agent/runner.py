"""Bounded runner for autonomous cycles.

It prevents overlapping cycles per symbol and deduplicates a snapshot hash.
It has no exchange or signing access.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from src.agent.context import PortfolioView
from src.agent.cycle import CycleResult, run_cycle
from src.agentic_engine import Policy
from src.market.models import MarketSnapshot
from src.providers.ports import AgentProvider


class CycleRunner:
    def __init__(self, provider: AgentProvider, policy: Policy) -> None:
        self.provider = provider
        self.policy = policy
        self._locks: dict[str, asyncio.Lock] = {}
        self._completed: set[str] = set()

    def _lock_for(self, symbol: str) -> asyncio.Lock:
        return self._locks.setdefault(symbol, asyncio.Lock())

    async def run_once(self, snapshot: MarketSnapshot, portfolio: PortfolioView,
                       now_ts_ms: int) -> CycleResult:
        cycle_id = snapshot.snapshot_hash or snapshot.computed_hash()
        lock = self._lock_for(snapshot.symbol)
        if lock.locked():
            return CycleResult("SKIPPED", "OVERLAPPING_CYCLE", cycle_id)
        if cycle_id in self._completed:
            return CycleResult("SKIPPED", "DUPLICATE_CYCLE", cycle_id)
        async with lock:
            if cycle_id in self._completed:
                return CycleResult("SKIPPED", "DUPLICATE_CYCLE", cycle_id)
            result = await run_cycle(self.provider, snapshot, portfolio, self.policy, now_ts_ms)
            self._completed.add(cycle_id)
            return result

    @property
    def completed_cycles(self) -> int:
        return len(self._completed)
