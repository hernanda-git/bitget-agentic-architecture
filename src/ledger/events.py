"""Typed, bounded runtime event contracts."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

EVENT_TYPES = frozenset({
    "MARKET_OBSERVED", "CONTEXT_BUILT", "AGENT_DECISION", "DECISION_REJECTED",
    "INTENT_APPROVED", "ORDER_SUBMITTED", "ORDER_ACKNOWLEDGED", "FILL_OBSERVED",
    "PROTECTION_REQUESTED", "PROTECTION_VERIFIED", "PROTECTION_FAILED",
    "POSITION_RECONCILED", "RECONCILIATION_DRIFT", "CIRCUIT_BREAKER",
    "KILL_SWITCH", "CYCLE_TERMINAL",
})
SCHEMA_VERSION = 1
MAX_PAYLOAD_BYTES = 64 * 1024
_HEX64 = set("0123456789abcdef")


def payload_digest(payload: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be JSON serializable") from exc
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError("payload exceeds bounded size")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    cycle_id: str
    trace_id: str
    created_ms: int
    mode: str
    product_type: str
    symbol: str
    payload: dict[str, Any]
    payload_hash: str
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RuntimeEvent":
        validate_event(value)
        payload = dict(value["payload"])
        digest = payload_digest(payload)
        supplied = value.get("payload_hash")
        if supplied is not None and supplied != digest:
            raise ValueError("payload_hash does not match payload")
        return cls(value["event_type"], value["cycle_id"], value["trace_id"], int(value["created_ms"]), value["mode"], value["product_type"], value["symbol"], payload, digest, int(value.get("schema_version", SCHEMA_VERSION)))

    def to_dict(self) -> dict[str, Any]:
        return {"event_type": self.event_type, "cycle_id": self.cycle_id, "trace_id": self.trace_id, "created_ms": self.created_ms, "mode": self.mode, "product_type": self.product_type, "symbol": self.symbol, "payload_hash": self.payload_hash, "schema_version": self.schema_version, "payload": self.payload}


def validate_event(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or value.get("event_type") not in EVENT_TYPES:
        raise ValueError("unknown event type")
    for field in ("cycle_id", "trace_id", "mode", "product_type", "symbol"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(f"missing {field}")
    if not isinstance(value.get("created_ms"), int) or value["created_ms"] <= 0:
        raise ValueError("invalid created_ms")
    if not isinstance(value.get("payload", {}), Mapping):
        raise ValueError("payload must be an object")
    version = value.get("schema_version", SCHEMA_VERSION)
    if not isinstance(version, int) or version < 1:
        raise ValueError("invalid schema_version")
    if "payload_hash" in value:
        digest = value["payload_hash"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in _HEX64 for c in digest):
            raise ValueError("invalid payload_hash")
