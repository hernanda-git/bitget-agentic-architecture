"""Small immutable typed row models used by the durable ledger."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LedgerIdentity:
    cycle_id: str
    trace_id: str
    created_ms: int
    mode: str
    product_type: str
    symbol: str
    payload_hash: str
    schema_version: int = 1


@dataclass(frozen=True)
class RunMetadata:
    trace_id: str
    cycle_id: str
    market_snapshot_id: str | None = None
    market_snapshot_hash: str | None = None
    context_hash: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    schema_version: int = 1
    decision_hash: str | None = None
    policy_version: str | None = None
    strategy_version: str | None = None
    intent_id: str | None = None
    client_order_id: str | None = None
    venue_order_id: str | None = None
    fill_ids: tuple[str, ...] = ()
    position_snapshot_id: str | None = None
    protection_snapshot_id: str | None = None


@dataclass(frozen=True)
class LedgerRow(LedgerIdentity):
    payload: dict[str, Any]


@dataclass(frozen=True)
class Order(LedgerRow):
    client_order_id: str = ""
    venue_order_id: str | None = None


@dataclass(frozen=True)
class Fill(LedgerRow):
    fill_id: str = ""
    client_order_id: str | None = None
