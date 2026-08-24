import pytest

from src.agentic_engine import Action
from src.decision_parser import DecisionParseError, parse_decision


NOW = 1_000
BASE = {
    "decision_id": "decision-1234",
    "action": "ENTER",
    "symbol": "BTCUSDT",
    "side": "BUY",
    "entry": 64000,
    "stop_loss": 63500,
    "take_profit": 65000,
    "leverage": 2,
    "max_notional_usd": 20,
    "valid_until_ms": 2000,
    "thesis": "trend continuation",
    "invalidation": "close below stop",
}


def test_strict_valid_decision():
    result = parse_decision(BASE, NOW)
    assert result.action is Action.ENTER
    assert result.symbol == "BTCUSDT"


@pytest.mark.parametrize("field", ["decision_id", "action", "symbol", "side", "entry", "stop_loss", "take_profit", "leverage", "max_notional_usd", "valid_until_ms", "thesis", "invalidation"])
def test_missing_required_field_is_rejected(field):
    payload = dict(BASE)
    del payload[field]
    with pytest.raises(DecisionParseError):
        parse_decision(payload, NOW)


def test_unknown_field_is_rejected():
    payload = dict(BASE, confidence=0.99)
    with pytest.raises(DecisionParseError, match="unknown"):
        parse_decision(payload, NOW)


def test_expired_decision_is_rejected():
    with pytest.raises(DecisionParseError, match="expired"):
        parse_decision(dict(BASE, valid_until_ms=NOW), NOW)


def test_hold_can_have_null_trade_levels():
    payload = dict(BASE, action="HOLD", side="NONE", entry=None, stop_loss=None, take_profit=None)
    result = parse_decision(payload, NOW)
    assert result.action is Action.HOLD


def test_invalid_json_is_rejected():
    with pytest.raises(DecisionParseError, match="JSON"):
        parse_decision("not json", NOW)
