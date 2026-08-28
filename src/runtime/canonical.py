"""Canonical offline lifecycle for paper and fixture-shadow modes.

The adapter owns composition and mode boundaries while delegating paper execution
to the existing runtime. It intentionally does not implement an exchange or ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agent.context import PortfolioView
from src.agentic_engine import Policy
from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.ledger.events import RuntimeEvent
from src.market.models import MarketSnapshot
from src.policy.breakers import BreakerRegistry
from src.providers.ports import AgentProvider
from src.runtime.heartbeat import HeartbeatMonitor
from src.runtime.paper_runtime import AutonomousPaperRuntime
from src.runtime.resource_monitor import ResourceMonitor


@dataclass
class CanonicalOfflineRuntime:
    """Single lifecycle entry point for offline paper and fixture observations."""

    mode: str
    ledger: EventLedger
    paper_runtime: AutonomousPaperRuntime | None = None
    _heartbeat: HeartbeatMonitor | None = None
    _resource_monitor: ResourceMonitor | None = None

    @classmethod
    def paper(cls, provider: AgentProvider, policy: Policy, ledger: EventLedger,
              exchange: FakeExchange | None = None, *, breakers: BreakerRegistry | None = None,
              heartbeat: HeartbeatMonitor | None = None,
              resource_monitor: ResourceMonitor | None = None,
              **runtime_options: Any) -> "CanonicalOfflineRuntime":
        return cls("paper", ledger, AutonomousPaperRuntime(
            provider, policy, ledger, exchange, breakers=breakers,
            heartbeat=heartbeat, resource_monitor=resource_monitor, **runtime_options
        ))

    @classmethod
    def fixture_shadow(cls, ledger: EventLedger, *, heartbeat: HeartbeatMonitor | None = None,
                      resource_monitor: ResourceMonitor | None = None) -> "CanonicalOfflineRuntime":
        rt = cls("fixture-shadow", ledger)
        rt._heartbeat = heartbeat
        rt._resource_monitor = resource_monitor
        return rt

    async def process(self, snapshot: MarketSnapshot, portfolio: PortfolioView | None = None,
                      now_ts_ms: int | None = None, attach_protection: bool = True) -> dict[str, Any]:
        cycle_id = snapshot.snapshot_hash or snapshot.computed_hash()
        # Claiming is performed by the paper runtime. Checking first prevents a
        # duplicate replay from adding a second terminal disposition.
        if self.ledger.cycle_status(cycle_id) is not None:
            return {"status": "SKIPPED", "reason": "DUPLICATE_CYCLE", "cycle_id": cycle_id}
        if self.mode == "paper":
            assert self.paper_runtime is not None
            return await self.paper_runtime.process(snapshot, portfolio, now_ts_ms, attach_protection)
        if self.mode != "fixture-shadow":
            raise ValueError(f"unsupported offline mode: {self.mode}")
        now_ts_ms = now_ts_ms if now_ts_ms is not None else snapshot.observed_ts_ms
        if not self.ledger.claim_cycle(cycle_id, mode=self.mode, symbol=snapshot.symbol):
            return {"status": "SKIPPED", "reason": "DUPLICATE_CYCLE", "cycle_id": cycle_id}
        identity = {"cycle_id": cycle_id, "trace_id": cycle_id, "created_ms": max(1, now_ts_ms),
                    "mode": self.mode, "product_type": "SUSDT-FUTURES", "symbol": snapshot.symbol}
        for event_type, payload in (
            ("MARKET_OBSERVED", {"cycle_id": cycle_id, "symbol": snapshot.symbol, "snapshot_hash": cycle_id, "mode": self.mode}),
            ("SHADOW_TICK_OBSERVED", {"cycle_id": cycle_id, "symbol": snapshot.symbol, "source": "fixture", "mode": self.mode}),
            ("CYCLE_TERMINAL", {"cycle_id": cycle_id, "disposition": "SHADOW_ONLY", "mode": self.mode}),
        ):
            self.ledger.append_event(RuntimeEvent.from_dict({"event_type": event_type, **identity, "payload": payload}))
        self.ledger.set_terminal(cycle_id, "SHADOW_ONLY")
        return {"status": "SHADOW_ONLY", "mode": self.mode, "cycle_id": cycle_id,
                "orders_placed": 0, "network_calls": 0, "signed_calls": 0}

    def tick_monitors(self) -> None:
        """Live monitor-loop step.

        For paper mode it delegates to the runtime; for fixture-shadow it ticks
        the monitors attached at construction. No signed calls, no credentials.
        """
        if self.paper_runtime is not None:
            self.paper_runtime.tick_monitors()
        else:
            if self._heartbeat is not None:
                self._heartbeat.tick()
            if self._resource_monitor is not None:
                self._resource_monitor.tick()
