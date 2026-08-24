import json
from pathlib import Path

import pytest

from src.ledger.events import EVENT_TYPES, RuntimeEvent, validate_event


def base(**overrides):
    value = {
        "event_type": "MARKET_OBSERVED",
        "cycle_id": "c1",
        "trace_id": "t1",
        "created_ms": 1700000000000,
        "mode": "paper",
        "product_type": "SUSDT-FUTURES",
        "symbol": "BTCUSDT",
        "payload": {"mark": 100},
    }
    value.update(overrides)
    return value


def test_event_types_are_closed_and_schema_is_versioned():
    assert len(EVENT_TYPES) == 16
    schema = json.loads(Path("schemas/runtime-event.schema.json").read_text())
    assert schema["$id"].endswith("runtime-event.schema.json")
    assert set(EVENT_TYPES) <= set(schema["properties"]["event_type"]["enum"])


@pytest.mark.parametrize("bad", [
    {"event_type": "NOPE"},
    {"event_type": "MARKET_OBSERVED", "cycle_id": ""},
    {"event_type": "MARKET_OBSERVED", "created_ms": None},
    {"event_type": "MARKET_OBSERVED", "payload_hash": "bad"},
])
def test_invalid_event_contracts_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_event(base(**bad))


def test_payload_is_bounded_and_hash_is_canonical():
    item = RuntimeEvent.from_dict(base())
    assert len(item.payload_hash) == 64
    assert item.to_dict()["payload_hash"] == item.payload_hash
    with pytest.raises(ValueError):
        RuntimeEvent.from_dict(base(payload={"x": "a" * 200_000}))


def test_explicit_hash_must_match_payload():
    with pytest.raises(ValueError):
        RuntimeEvent.from_dict(base(payload_hash="0" * 64))
