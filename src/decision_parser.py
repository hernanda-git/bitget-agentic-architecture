"""Strict, non-repairing parser for provider decisions."""
from __future__ import annotations

import json
from typing import Any

from src.agentic_engine import Action, AgentDecision


class DecisionParseError(ValueError):
    pass


_ALLOWED = {
    "decision_id", "action", "symbol", "side", "entry", "stop_loss",
    "take_profit", "leverage", "max_notional_usd", "valid_until_ms",
    "thesis", "invalidation",
}
_ACTIONS = {item.value for item in Action}
_SIDES = {"BUY", "SELL", "NONE"}


def _number(value: Any, field: str, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DecisionParseError(f"{field} must be numeric")
    value = float(value)
    if value <= 0:
        raise DecisionParseError(f"{field} must be positive")
    return value


def parse_decision(raw: str | dict[str, Any], now_ms: int) -> AgentDecision:
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DecisionParseError("invalid JSON") from exc
    else:
        obj = raw
    if not isinstance(obj, dict):
        raise DecisionParseError("decision must be an object")
    unknown = set(obj) - _ALLOWED
    if unknown:
        raise DecisionParseError(f"unknown fields: {sorted(unknown)}")
    missing = _ALLOWED - set(obj)
    if missing:
        raise DecisionParseError(f"missing fields: {sorted(missing)}")
    decision_id = obj["decision_id"]
    if not isinstance(decision_id, str) or not 8 <= len(decision_id) <= 128:
        raise DecisionParseError("invalid decision_id")
    action = obj["action"]
    if action not in _ACTIONS:
        raise DecisionParseError("invalid action")
    symbol = obj["symbol"]
    if not isinstance(symbol, str) or not symbol.isupper() or not symbol.endswith("USDT"):
        raise DecisionParseError("invalid symbol")
    side = obj["side"]
    if side not in _SIDES:
        raise DecisionParseError("invalid side")
    entry = _number(obj["entry"], "entry", nullable=True)
    stop_loss = _number(obj["stop_loss"], "stop_loss", nullable=True)
    take_profit = _number(obj["take_profit"], "take_profit", nullable=True)
    leverage = _number(obj["leverage"], "leverage")
    notional = _number(obj["max_notional_usd"], "max_notional_usd")
    expiry = obj["valid_until_ms"]
    if isinstance(expiry, bool) or not isinstance(expiry, int) or expiry <= now_ms:
        raise DecisionParseError("decision expired or invalid")
    thesis = obj["thesis"]
    invalidation = obj["invalidation"]
    if not isinstance(thesis, str) or not thesis or len(thesis) > 2000:
        raise DecisionParseError("invalid thesis")
    if not isinstance(invalidation, str) or not invalidation or len(invalidation) > 1000:
        raise DecisionParseError("invalid invalidation")
    if action == Action.ENTER.value:
        if side not in {"BUY", "SELL"} or entry is None or stop_loss is None or take_profit is None:
            raise DecisionParseError("ENTER requires side, entry, stop_loss, and take_profit")
    return AgentDecision(decision_id, Action(action), symbol, side, entry, stop_loss,
                         take_profit, leverage, notional, expiry, thesis, invalidation)
