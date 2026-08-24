"""Fail-closed semantic policy for SUSDT-FUTURES proposals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet

from src.agentic_engine import Action, AgentDecision, MarketSnapshot

PRODUCT_TYPE = "SUSDT-FUTURES"


@dataclass(frozen=True)
class SemanticPolicy:
    allow_symbols: FrozenSet[str]
    now_ms: int
    product_type: str = PRODUCT_TYPE
    max_entry_distance_bps: float = 100.0
    max_slippage_bps: float = 50.0
    max_funding_bps: float = 100.0
    max_fee_bps: float = 100.0
    max_leverage: float = 10.0
    min_notional_usd: float = 0.0
    max_notional_usd: float = float("inf")
    max_daily_loss_usd: float = float("inf")
    max_drawdown_pct: float = 100.0
    max_concurrent_positions: int = 100
    max_spread_bps: float = 20.0


@dataclass(frozen=True)
class SemanticState:
    daily_loss_usd: float = 0.0
    drawdown_pct: float = 0.0
    concurrent_positions: int = 0
    existing_symbols: FrozenSet[str] = field(default_factory=frozenset)
    protection_verified: bool = True
    reconciliation_degraded: bool = False
    provider_circuit_open: bool = False
    kill_switch_active: bool = False
    slippage_bps: float = 0.0
    funding_bps: float = 0.0
    fee_bps: float = 0.0


@dataclass(frozen=True)
class SemanticResult:
    approved: bool
    code: str
    details: str = ""


def _reject(code: str, details: str = "") -> SemanticResult:
    return SemanticResult(False, code, details)


def validate_semantic(decision: AgentDecision, market: MarketSnapshot,
                      policy: SemanticPolicy, state: SemanticState | None = None) -> SemanticResult:
    """Validate a decision without network or execution side effects."""
    state = state or SemanticState()
    if policy.product_type != PRODUCT_TYPE:
        return _reject("PRODUCT_TYPE_UNSUPPORTED")
    if state.kill_switch_active:
        return _reject("KILL_SWITCH_ACTIVE")
    if state.provider_circuit_open:
        return _reject("PROVIDER_CIRCUIT_OPEN")
    if state.reconciliation_degraded:
        return _reject("RECONCILIATION_DEGRADED")
    if decision.action == Action.HOLD:
        return SemanticResult(True, "HOLD")
    if decision.action not in {Action.ENTER, Action.EXIT, Action.REDUCE, Action.CANCEL}:
        return _reject("ACTION_UNSUPPORTED")
    if decision.symbol not in policy.allow_symbols:
        return _reject("SYMBOL_NOT_ALLOWED")
    if market.symbol != decision.symbol:
        return _reject("MARKET_SYMBOL_MISMATCH")
    if market.age_seconds < 0:
        return _reject("MARKET_AGE_INVALID")
    if market.age_seconds > 3.0:
        return _reject("STALE_MARKET_DATA")
    if market.spread_bps > policy.max_spread_bps:
        return _reject("SPREAD_TOO_WIDE")
    if decision.valid_until_ms <= policy.now_ms:
        return _reject("DECISION_EXPIRED")
    if decision.action != Action.ENTER:
        return SemanticResult(True, "APPROVED")
    if decision.side not in {"BUY", "SELL"}:
        return _reject("SIDE_INVALID")
    if decision.entry is None or decision.entry <= 0:
        return _reject("ENTRY_REQUIRED")
    if market.mark_price <= 0:
        return _reject("MARK_PRICE_INVALID")
    distance_bps = abs(decision.entry - market.mark_price) / market.mark_price * 10_000
    if distance_bps > policy.max_entry_distance_bps:
        return _reject("ENTRY_TOO_FAR_FROM_MARK")
    if decision.stop_loss is None or decision.take_profit is None:
        return _reject("PROTECTION_REQUIRED")
    if decision.side == "BUY" and not (decision.stop_loss < decision.entry < decision.take_profit):
        return _reject("LONG_LEVELS_INVALID")
    if decision.side == "SELL" and not (decision.take_profit < decision.entry < decision.stop_loss):
        return _reject("SHORT_LEVELS_INVALID")
    if abs(state.slippage_bps) > policy.max_slippage_bps:
        return _reject("SLIPPAGE_TOO_HIGH")
    if abs(state.funding_bps) > policy.max_funding_bps:
        return _reject("FUNDING_TOO_HIGH")
    if state.fee_bps > policy.max_fee_bps:
        return _reject("FEE_NOT_VIABLE")
    if decision.leverage <= 0 or decision.leverage > policy.max_leverage:
        return _reject("LEVERAGE_LIMIT")
    if decision.max_notional_usd < policy.min_notional_usd:
        return _reject("MIN_NOTIONAL")
    if decision.max_notional_usd > policy.max_notional_usd:
        return _reject("MAX_NOTIONAL")
    if state.daily_loss_usd >= policy.max_daily_loss_usd:
        return _reject("DAILY_LOSS_LIMIT")
    if state.drawdown_pct >= policy.max_drawdown_pct:
        return _reject("DRAWDOWN_LIMIT")
    if state.concurrent_positions >= policy.max_concurrent_positions:
        return _reject("CONCURRENT_POSITIONS_LIMIT")
    if decision.symbol in state.existing_symbols:
        return _reject("DUPLICATE_EXPOSURE")
    if not state.protection_verified:
        return _reject("PROTECTION_UNVERIFIED")
    return SemanticResult(True, "APPROVED")


# Compatibility-friendly name for callers that prefer a policy verb.
validate_policy = validate_semantic
