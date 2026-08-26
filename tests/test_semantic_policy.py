from dataclasses import replace

from src.agentic_engine import Action, AgentDecision, MarketSnapshot
from src.policy.semantic import SemanticPolicy, SemanticState, validate_semantic
from src.policy.semantic import POLICY_REJECTION_CODES, is_stable_policy_code


def decision(**changes):
    base = AgentDecision(
        decision_id="d-1", action=Action.ENTER, symbol="BTCUSDT", side="BUY",
        entry=100.0, stop_loss=95.0, take_profit=110.0, leverage=2.0,
        max_notional_usd=100.0, valid_until_ms=2_000, thesis="x", invalidation="y",
    )
    return replace(base, **changes)


def market(**changes):
    base = MarketSnapshot("BTCUSDT", 100.0, 99.9, 100.1, 0.2, 20.0)
    return replace(base, **changes)


def policy(**changes):
    base = SemanticPolicy(allow_symbols=frozenset({"BTCUSDT"}), now_ms=1_000)
    return replace(base, **changes)


def test_valid_susdt_enter_is_approved():
    result = validate_semantic(decision(), market(), policy(), SemanticState())
    assert result.approved is True
    assert result.code == "APPROVED"


def test_product_type_must_be_exact_susdt_futures():
    result = validate_semantic(decision(), market(), policy(product_type="USDT-FUTURES"), SemanticState())
    assert (result.approved, result.code) == (False, "PRODUCT_TYPE_UNSUPPORTED")


def test_semantic_checks_cover_mark_expiry_cost_and_exposure():
    cases = [
        (decision(entry=120), market(), "ENTRY_TOO_FAR_FROM_MARK"),
        (decision(valid_until_ms=999), market(), "DECISION_EXPIRED"),
        (decision(), market(spread_bps=99), "SPREAD_TOO_WIDE"),
        (decision(), market(), "DUPLICATE_EXPOSURE"),
    ]
    states = [SemanticState(), SemanticState(), SemanticState(), SemanticState(existing_symbols=frozenset({"BTCUSDT"}))]
    for (dec, mkt, code), state in zip(cases, states):
        result = validate_semantic(dec, mkt, policy(), state)
        assert result.code == code


def test_breaker_and_kill_switch_reject_entries_with_stable_codes():
    for state, code in [
        (SemanticState(provider_circuit_open=True), "PROVIDER_CIRCUIT_OPEN"),
        (SemanticState(reconciliation_degraded=True), "RECONCILIATION_DEGRADED"),
        (SemanticState(kill_switch_active=True), "KILL_SWITCH_ACTIVE"),
    ]:
        assert validate_semantic(decision(), market(), policy(), state).code == code


def test_hold_is_safe_without_entry_geometry():
    result = validate_semantic(decision(action=Action.HOLD, side="NONE", entry=None, stop_loss=None, take_profit=None), market(), policy(), SemanticState())
    assert (result.approved, result.code) == (True, "HOLD")


def test_every_semantic_rejection_is_a_stable_machine_code():
    cases = [
        (policy(product_type="USDT-FUTURES"), SemanticState(), decision()),
        (policy(), SemanticState(kill_switch_active=True), decision()),
        (policy(), SemanticState(), decision(symbol="ETHUSDT")),
        (policy(), SemanticState(), decision(entry=120)),
        (policy(), SemanticState(), decision(stop_loss=101)),
        (policy(), SemanticState(), decision(leverage=99)),
        (policy(), SemanticState(), decision(max_notional_usd=0.1)),
    ]
    for pol, state, dec in cases:
        result = validate_semantic(dec, market(), pol, state)
        assert not result.approved
        assert is_stable_policy_code(result.code)
        assert result.code in POLICY_REJECTION_CODES
