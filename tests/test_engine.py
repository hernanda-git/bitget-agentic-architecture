from src.agentic_engine import Action, AgentDecision, MarketSnapshot, Policy, validate_decision
from src.policy.semantic import POLICY_REJECTION_CODES, is_stable_policy_code


def decision(**overrides):
    values = dict(
        decision_id="decision-123456",
        action=Action.ENTER,
        symbol="BTCUSDT",
        side="BUY",
        entry=64000,
        stop_loss=63500,
        take_profit=65000,
        leverage=2,
        max_notional_usd=20,
        valid_until_ms=9999999999999,
        thesis="test",
        invalidation="below stop",
    )
    values.update(overrides)
    return AgentDecision(**values)


def policy(**overrides):
    values = dict(
        allow_symbols=frozenset({"BTCUSDT"}),
        max_leverage=3,
        max_position_notional_usd=25,
        max_spread_bps=20,
        max_snapshot_age_seconds=3,
        kill_switch=False,
    )
    values.update(overrides)
    return Policy(**values)


def market(**overrides):
    values = dict(symbol="BTCUSDT", mark_price=64000, bid=63990, ask=64010, age_seconds=0.2, spread_bps=3)
    values.update(overrides)
    return MarketSnapshot(**values)


def test_valid_enter_is_approved():
    assert validate_decision(decision(), market(), policy()) == (True, "APPROVED")


def test_kill_switch_rejects_without_human_trade_approval():
    assert validate_decision(decision(), market(), policy(kill_switch=True)) == (False, "KILL_SWITCH")


def test_agent_cannot_exceed_leverage_or_notional():
    assert validate_decision(decision(leverage=4), market(), policy()) == (False, "LEVERAGE_LIMIT")
    assert validate_decision(decision(max_notional_usd=26), market(), policy()) == (False, "NOTIONAL_LIMIT")


def test_stale_market_is_fail_closed():
    assert validate_decision(decision(), market(age_seconds=4), policy()) == (False, "STALE_MARKET_DATA")


def test_wrong_long_levels_are_rejected():
    assert validate_decision(decision(stop_loss=64500), market(), policy()) == (False, "LONG_LEVELS_INVALID")


def test_hold_does_not_create_order_requirements():
    ok, reason = validate_decision(decision(action=Action.HOLD, side="NONE", entry=None, stop_loss=None, take_profit=None), market(), policy())
    assert (ok, reason) == (True, "HOLD")


def test_engine_rejections_use_the_same_canonical_code_set():
    for kwargs in ({"symbol": "ETHUSDT"}, {"leverage": 4}, {"max_notional_usd": 26}, {"entry": 65000}):
        ok, reason = validate_decision(decision(**kwargs), market(), policy())
        assert ok is False
        assert is_stable_policy_code(reason)
        assert reason in POLICY_REJECTION_CODES
