"""Fail-closed semantic policy for SUSDT-FUTURES proposals."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import FrozenSet, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from src.agentic_engine import AgentDecision, MarketSnapshot


class PolicyRejectionCode(str, Enum):
    """Closed, provider-independent vocabulary for unsafe proposals."""
    PRODUCT_TYPE_UNSUPPORTED = "PRODUCT_TYPE_UNSUPPORTED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    KILL_SWITCH = "KILL_SWITCH"
    PROVIDER_CIRCUIT_OPEN = "PROVIDER_CIRCUIT_OPEN"
    RECONCILIATION_DEGRADED = "RECONCILIATION_DEGRADED"
    SYMBOL_NOT_ALLOWED = "SYMBOL_NOT_ALLOWED"
    MARKET_SYMBOL_MISMATCH = "MARKET_SYMBOL_MISMATCH"
    MARKET_AGE_INVALID = "MARKET_AGE_INVALID"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    DECISION_EXPIRED = "DECISION_EXPIRED"
    ACTION_UNSUPPORTED = "ACTION_UNSUPPORTED"
    SIDE_INVALID = "SIDE_INVALID"
    SIDE_REQUIRED = "SIDE_REQUIRED"
    ENTRY_REQUIRED = "ENTRY_REQUIRED"
    MARK_PRICE_INVALID = "MARK_PRICE_INVALID"
    ENTRY_TOO_FAR_FROM_MARK = "ENTRY_TOO_FAR_FROM_MARK"
    PROTECTION_REQUIRED = "PROTECTION_REQUIRED"
    STOP_LOSS_REQUIRED = "STOP_LOSS_REQUIRED"
    TAKE_PROFIT_REQUIRED = "TAKE_PROFIT_REQUIRED"
    LONG_LEVELS_INVALID = "LONG_LEVELS_INVALID"
    SHORT_LEVELS_INVALID = "SHORT_LEVELS_INVALID"
    SLIPPAGE_TOO_HIGH = "SLIPPAGE_TOO_HIGH"
    FUNDING_TOO_HIGH = "FUNDING_TOO_HIGH"
    FEE_NOT_VIABLE = "FEE_NOT_VIABLE"
    LEVERAGE_LIMIT = "LEVERAGE_LIMIT"
    MIN_NOTIONAL = "MIN_NOTIONAL"
    MAX_NOTIONAL = "MAX_NOTIONAL"
    NOTIONAL_LIMIT = "NOTIONAL_LIMIT"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    CONCURRENT_POSITIONS_LIMIT = "CONCURRENT_POSITIONS_LIMIT"
    GROSS_EXPOSURE_LIMIT = "GROSS_EXPOSURE_LIMIT"
    NET_EXPOSURE_LIMIT = "NET_EXPOSURE_LIMIT"
    CORRELATED_EXPOSURE_LIMIT = "CORRELATED_EXPOSURE_LIMIT"
    SYMBOL_CONCENTRATION_LIMIT = "SYMBOL_CONCENTRATION_LIMIT"
    DUPLICATE_EXPOSURE = "DUPLICATE_EXPOSURE"
    PROTECTION_UNVERIFIED = "PROTECTION_UNVERIFIED"


POLICY_REJECTION_CODES = frozenset(code.value for code in PolicyRejectionCode)


def is_stable_policy_code(code: str) -> bool:
    return isinstance(code, str) and code in POLICY_REJECTION_CODES

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
    min_notional_usd: float = 1.0
    max_notional_usd: float = 1000.0
    max_total_notional_usd: float = 2000.0
    max_correlated_notional_usd: float = 1500.0
    max_symbol_notional_usd: float = 1000.0
    max_daily_loss_usd: float = 100.0
    max_drawdown_pct: float = 20.0
    max_concurrent_positions: int = 10
    max_orders_per_minute: int = 60
    max_spread_bps: float = 20.0

    def __post_init__(self) -> None:
        for name in ("max_leverage", "min_notional_usd", "max_notional_usd", "max_total_notional_usd",
                     "max_correlated_notional_usd", "max_symbol_notional_usd",
                     "max_daily_loss_usd", "max_drawdown_pct", "max_spread_bps"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.max_concurrent_positions <= 0 or self.max_orders_per_minute <= 0:
            raise ValueError("count limits must be positive")


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
    gross_notional: float = 0.0
    net_notional: float = 0.0
    correlated_notional: float = 0.0
    symbol_notional: float = 0.0


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
    # Lazy import avoids a policy/engine import cycle while keeping the policy
    # vocabulary the single source of truth for both entry points.
    from src.agentic_engine import Action
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
    if state.gross_notional >= policy.max_total_notional_usd:
        return _reject("GROSS_EXPOSURE_LIMIT")
    if abs(state.net_notional) >= policy.max_total_notional_usd:
        return _reject("NET_EXPOSURE_LIMIT")
    if state.correlated_notional >= policy.max_correlated_notional_usd:
        return _reject("CORRELATED_EXPOSURE_LIMIT")
    if state.symbol_notional >= policy.max_symbol_notional_usd:
        return _reject("SYMBOL_CONCENTRATION_LIMIT")
    if decision.symbol in state.existing_symbols:
        return _reject("DUPLICATE_EXPOSURE")
    if not state.protection_verified:
        return _reject("PROTECTION_UNVERIFIED")
    return SemanticResult(True, "APPROVED")


# Compatibility-friendly name for callers that prefer a policy verb.
validate_policy = validate_semantic
