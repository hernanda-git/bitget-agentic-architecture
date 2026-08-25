"""Dependency-free safe scaffold for the fully agentic decision boundary.

This module intentionally does not call Bitget or an AI provider. It demonstrates
where deterministic policy must sit between an autonomous model and execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    ENTER = "ENTER"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    HOLD = "HOLD"
    CANCEL = "CANCEL"


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    mark_price: float
    bid: float
    ask: float
    age_seconds: float
    spread_bps: float


@dataclass(frozen=True)
class AgentDecision:
    decision_id: str
    action: Action
    symbol: str
    side: str
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    leverage: float
    max_notional_usd: float
    valid_until_ms: int
    thesis: str
    invalidation: str


@dataclass(frozen=True)
class Policy:
    allow_symbols: frozenset[str]
    max_leverage: float
    max_position_notional_usd: float
    max_spread_bps: float
    max_snapshot_age_seconds: float
    require_stop_loss: bool = True
    require_take_profit: bool = True
    kill_switch: bool = True
    requested_risk_usd: float = 1.0
    quantity_step: float = 0.001
    min_notional_usd: float = 1.0
    max_total_notional_usd: float = 25.0
    available_equity_usd: float = 10000.0
    contract_multiplier: float = 1.0


def validate_decision(decision: AgentDecision, market: MarketSnapshot, policy: Policy) -> tuple[bool, str]:
    """Fail-closed semantic validation. No network and no order side effects."""
    if policy.kill_switch:
        return False, "KILL_SWITCH"
    if decision.action == Action.HOLD:
        return True, "HOLD"
    if decision.symbol not in policy.allow_symbols:
        return False, "SYMBOL_NOT_ALLOWED"
    if market.symbol != decision.symbol:
        return False, "MARKET_SYMBOL_MISMATCH"
    if market.age_seconds > policy.max_snapshot_age_seconds:
        return False, "STALE_MARKET_DATA"
    if market.spread_bps > policy.max_spread_bps:
        return False, "SPREAD_TOO_WIDE"
    if decision.leverage <= 0 or decision.leverage > policy.max_leverage:
        return False, "LEVERAGE_LIMIT"
    if decision.max_notional_usd <= 0 or decision.max_notional_usd > policy.max_position_notional_usd:
        return False, "NOTIONAL_LIMIT"
    if decision.action == Action.ENTER:
        if decision.side not in {"BUY", "SELL"}:
            return False, "SIDE_REQUIRED"
        if decision.entry is None or decision.entry <= 0:
            return False, "ENTRY_REQUIRED"
        if policy.require_stop_loss and (decision.stop_loss is None or decision.stop_loss <= 0):
            return False, "STOP_LOSS_REQUIRED"
        if policy.require_take_profit and (decision.take_profit is None or decision.take_profit <= 0):
            return False, "TAKE_PROFIT_REQUIRED"
        assert decision.stop_loss is not None
        assert decision.take_profit is not None
        if decision.side == "BUY" and not (decision.stop_loss < decision.entry < decision.take_profit):
            return False, "LONG_LEVELS_INVALID"
        if decision.side == "SELL" and not (decision.take_profit < decision.entry < decision.stop_loss):
            return False, "SHORT_LEVELS_INVALID"
    return True, "APPROVED"


def main() -> None:
    market = MarketSnapshot("BTCUSDT", 64000, 63990, 64010, 0.2, 3.1)
    decision = AgentDecision(
        "demo-decision-001", Action.ENTER, "BTCUSDT", "BUY", 64000,
        63500, 65000, 2, 20, 9999999999999, "demo", "below stop"
    )
    policy = Policy(frozenset({"BTCUSDT"}), 3, 25, 20, 3, kill_switch=False)
    print(validate_decision(decision, market, policy))


if __name__ == "__main__":
    main()
