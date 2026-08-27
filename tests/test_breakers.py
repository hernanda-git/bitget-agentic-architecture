from pathlib import Path

from src.policy.breakers import BreakerRegistry, BreakerStore


def test_breaker_state_persists_and_any_open_breaker_parks_entries(tmp_path: Path):
    store = BreakerStore(tmp_path / "breakers.json")
    registry = BreakerRegistry(store)
    registry.trip("provider", "timeouts")
    registry.trip("daily_loss", "cap reached")
    assert registry.entries_parked() is True
    assert registry.reason_codes() == ["DAILY_LOSS_BREAKER", "PROVIDER_BREAKER"]

    reopened = BreakerRegistry(BreakerStore(tmp_path / "breakers.json"))
    assert reopened.entries_parked() is True
    assert reopened.is_open("provider") is True


def test_model_cannot_clear_breaker_but_operator_can(tmp_path: Path):
    registry = BreakerRegistry(BreakerStore(tmp_path / "breakers.json"))
    registry.trip("heartbeat", "missing")
    try:
        registry.clear("heartbeat", actor="model")
    except PermissionError:
        pass
    else:
        raise AssertionError("model must not clear breakers")
    assert registry.is_open("heartbeat")
    registry.clear("heartbeat", actor="operator")
    assert not registry.is_open("heartbeat")


def test_unknown_breaker_is_rejected(tmp_path: Path):
    registry = BreakerRegistry(BreakerStore(tmp_path / "breakers.json"))
    try:
        registry.trip("unknown", "bad")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown breaker must be rejected")


def test_auto_recovery_can_clear_heartbeat_breaker_but_model_cannot(tmp_path: Path):
    """A verified automatic recovery (fresh heartbeat) may clear its own trip.

    The model must never clear breakers; the operator and a verified automatic
    recovery are the only allowed actors. This is the contract the runtime
    heartbeat monitor relies on to un-park entries after a stall recovers.
    """
    registry = BreakerRegistry(BreakerStore(tmp_path / "breakers.json"))
    registry.trip("heartbeat", "no heartbeat for 1500ms")
    try:
        registry.clear("heartbeat", actor="model")
    except PermissionError:
        pass
    else:
        raise AssertionError("model must not clear breakers")
    assert registry.is_open("heartbeat") is True
    # Verified automatic recovery is permitted (e.g. a fresh heartbeat observed).
    registry.clear("heartbeat", actor="auto_recovery")
    assert registry.is_open("heartbeat") is False
    # Unknown actors are still rejected.
    registry.trip("heartbeat", "again")
    try:
        registry.clear("heartbeat", actor="self_heal")
    except PermissionError:
        pass
    else:
        raise AssertionError("only operator/auto_recovery may clear breakers")
