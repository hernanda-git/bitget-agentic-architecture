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
