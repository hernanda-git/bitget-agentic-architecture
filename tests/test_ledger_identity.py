import pytest

from src.ledger.events import RuntimeEvent, payload_digest
from src.ledger.sqlite import EventLedger


def canonical(**overrides):
    value = {
        "event_type": "AGENT_DECISION",
        "cycle_id": "cycle-1",
        "trace_id": "trace-1",
        "created_ms": 1700000000000,
        "mode": "paper",
        "product_type": "SUSDT-FUTURES",
        "symbol": "BTCUSDT",
        "payload": {"action": "HOLD"},
    }
    value.update(overrides)
    value.setdefault("payload_hash", payload_digest(value["payload"]))
    return value


def test_canonical_write_rejects_implicit_identity(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    for field in ("cycle_id", "trace_id", "mode", "product_type", "symbol", "created_ms"):
        value = canonical()
        value.pop(field)
        with pytest.raises(ValueError, match="missing"):
            ledger.append_event(value)


def test_canonical_write_accepts_explicit_identity_and_hash(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    event_id = ledger.append_event(canonical())
    stored = ledger.all()[0]
    assert event_id == 1
    assert stored["cycle_id"] == "cycle-1"
    assert stored["payload_hash"] == payload_digest(stored["payload"])
    assert not stored["cycle_id"].startswith("legacy-")


def test_legacy_adapter_is_explicit_and_keeps_historical_fixtures(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    with pytest.raises(ValueError):
        ledger.append_event({"event_type": "AGENT_DECISION", "payload": {"action": "HOLD"}})
    ledger.append_legacy("AGENT_DECISION", {"action": "HOLD"})
    assert ledger.all()[0]["cycle_id"].startswith("legacy-")


def test_runtime_event_still_normalizes_hash_for_historical_object_fixtures():
    event = RuntimeEvent.from_dict({**canonical()})
    assert event.payload_hash == payload_digest(event.payload)
