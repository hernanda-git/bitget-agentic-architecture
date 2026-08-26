"""Standalone offline autonomous paper runtime."""
from __future__ import annotations

from typing import Any

from src.agent.context import PortfolioView, build_context
from src.agentic_engine import Policy, MarketSnapshot as PolicyMarketSnapshot, validate_decision
from src.decision_parser import DecisionParseError, parse_decision
from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.ledger.events import RuntimeEvent
from src.market.freshness import check_freshness
from src.market.models import MarketSnapshot
from src.providers.circuit import ProviderCircuit
from src.providers.ports import AgentProvider, ProviderResponse
from src.reconcile.engine import reconcile_positions, verify_protection
from src.policy.sizing import size_for_risk


class AutonomousPaperRuntime:
    def __init__(self, provider: AgentProvider, policy: Policy, ledger: EventLedger,
                 exchange: FakeExchange | None = None, *, provider_timeout_seconds: float = 8.0,
                 provider_failure_threshold: int = 3) -> None:
        self.policy = policy
        self.ledger = ledger
        self.exchange = exchange or FakeExchange()
        if not isinstance(self.exchange, FakeExchange):
            raise TypeError("AutonomousPaperRuntime accepts FakeExchange only")
        self.circuit = provider if isinstance(provider, ProviderCircuit) else ProviderCircuit(
            provider, provider_timeout_seconds, provider_failure_threshold)
        self._event_context: dict[str, Any] = {}

    async def process(self, snapshot: MarketSnapshot, portfolio: PortfolioView | None = None,
                      now_ts_ms: int | None = None, attach_protection: bool = True) -> dict[str, Any]:
        portfolio = portfolio or PortfolioView()
        now_ts_ms = now_ts_ms if now_ts_ms is not None else snapshot.observed_ts_ms
        cycle_id = snapshot.snapshot_hash or snapshot.computed_hash()
        self._event_context = {
            "cycle_id": cycle_id,
            "trace_id": cycle_id,
            "created_ms": max(1, now_ts_ms),
            "mode": "paper",
            "product_type": "SUSDT-FUTURES",
            "symbol": snapshot.symbol,
        }
        if not self._claim(cycle_id):
            self._append("CYCLE_TERMINAL", {"cycle_id": cycle_id, "disposition": "SKIPPED", "reason": "DUPLICATE_CYCLE"})
            return {"status": "SKIPPED", "reason": "DUPLICATE_CYCLE", "cycle_id": cycle_id}
        self._append("MARKET_OBSERVED", {"cycle_id": cycle_id, "symbol": snapshot.symbol, "snapshot_hash": cycle_id})
        freshness = check_freshness(snapshot, now_ts_ms, self.policy.max_snapshot_age_seconds)
        if not freshness.ok:
            return self._terminal(cycle_id, "PARKED", freshness.reason)
        context = build_context(snapshot, portfolio, {
            "allow_symbols": sorted(self.policy.allow_symbols),
            "max_leverage": self.policy.max_leverage,
            "max_position_notional_usd": self.policy.max_position_notional_usd,
            "max_spread_bps": self.policy.max_spread_bps,
            "kill_switch": self.policy.kill_switch,
        })
        self._append("AGENT_CONTEXT_BUILT", {"cycle_id": cycle_id, "context_id": context.context_id})
        response = await self.circuit.decide(context)
        if response.status != "OK":
            code = response.error_code or response.status
            status = "PARKED_PROVIDER" if code == "PROVIDER_CIRCUIT_OPEN" else "NO_DECISION"
            return self._terminal(cycle_id, status, code)
        try:
            decision = parse_decision(response.content, now_ts_ms)
        except DecisionParseError as exc:
            self.circuit._failure("PROVIDER_MALFORMED")
            status = "PARKED_PROVIDER" if self.circuit.is_open else "NO_DECISION"
            return self._terminal(cycle_id, status, f"DECISION_PARSE:{exc}")
        self._append("AGENT_DECISION", {"cycle_id": cycle_id, "action": decision.action.value,
                                        "symbol": decision.symbol, "side": decision.side})
        market = PolicyMarketSnapshot(snapshot.symbol, snapshot.mark_price, snapshot.bid, snapshot.ask,
                                      (now_ts_ms - snapshot.observed_ts_ms) / 1000, snapshot.spread_bps)
        approved, reason = validate_decision(decision, market, self.policy)
        if not approved:
            return self._terminal(cycle_id, "HELD" if reason == "HOLD" else "REJECTED", reason)
        if decision.action.value != "ENTER":
            return self._terminal(cycle_id, "HELD", decision.action.value)
        assert decision.entry is not None
        assert decision.stop_loss is not None
        assert decision.take_profit is not None
        sizing = size_for_risk(side=decision.side, entry=decision.entry, stop_loss=decision.stop_loss,
                               requested_risk_usd=self.policy.requested_risk_usd,
                               min_notional_usd=max(self.policy.min_notional_usd, self.exchange.venue.minimum_notional),
                               max_notional_usd=min(self.policy.max_position_notional_usd, decision.max_notional_usd),
                               quantity_step=max(self.policy.quantity_step, self.exchange.venue.quantity_step),
                               contract_multiplier=self.policy.contract_multiplier,
                               available_equity_usd=self.policy.available_equity_usd,
                               existing_gross_notional_usd=sum(p.quantity * p.entry_price * self.exchange.venue.contract_multiplier for p in self.exchange.positions.values()),
                               max_total_notional_usd=self.policy.max_total_notional_usd)
        oid = "paper-" + cycle_id[:24]
        fill = self.exchange.place_order(oid, decision.symbol, decision.side, sizing.quantity, decision.entry)
        self._append("INTENT_APPROVED", {"cycle_id": cycle_id, "client_order_id": oid})
        self._append("ORDER_SUBMITTED", {"cycle_id": cycle_id, "client_order_id": oid})
        self._append("FILL_OBSERVED", {"cycle_id": cycle_id, "client_order_id": oid, "symbol": decision.symbol,
                                        "side": decision.side, "quantity": fill.quantity, "price": fill.price, "fee": fill.fee})
        if attach_protection:
            self.exchange.set_protection(decision.symbol, decision.stop_loss, decision.take_profit)
        pos = self.exchange.positions[decision.symbol]
        protected, protection_reason = verify_protection({"symbol": pos.symbol, "quantity": pos.quantity,
            "stop_loss": pos.stop_loss, "take_profit": pos.take_profit})
        self._append("PROTECTION_VERIFIED" if protected else "PROTECTION_FAILED",
                     {"cycle_id": cycle_id, "status": protection_reason})
        local = {decision.symbol: {"quantity": pos.quantity, "side": pos.side}}
        rec = reconcile_positions(local, local)
        self._append("POSITION_RECONCILED", {"cycle_id": cycle_id, "in_sync": rec.in_sync, "reasons": rec.reasons})
        status = "EXECUTED" if protected and rec.in_sync else "DEGRADED"
        return self._terminal(cycle_id, status, "", protection=protection_reason, reconciled=rec.in_sync)

    def _claim(self, cycle_id: str) -> bool:
        return bool(self.ledger.claim_cycle(cycle_id))

    def _append(self, event_type: str, payload: dict[str, Any]) -> None:
        value = {"event_type": event_type, **self._event_context, "payload": payload}
        self.ledger.append_event(RuntimeEvent.from_dict(value))

    def _terminal(self, cycle_id: str, status: str, reason: str, **extra: Any) -> dict[str, Any]:
        payload = {"cycle_id": cycle_id, "disposition": status}
        if reason:
            payload["reason"] = reason
        self._append("CYCLE_TERMINAL", payload)
        setter = getattr(self.ledger, "set_terminal", None)
        if callable(setter):
            setter(cycle_id, status)
        return {"status": status, "cycle_id": cycle_id, **({"reason": reason} if reason else {}), **extra}
