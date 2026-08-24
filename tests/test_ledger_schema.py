import sqlite3

import pytest

from src.ledger.sqlite import EventLedger


def event(cycle_id="c1", event_type="AGENT_DECISION", **payload):
    return {
        "event_type": event_type,
        "cycle_id": cycle_id,
        "trace_id": "t-" + cycle_id,
        "created_ms": 1700000000000,
        "mode": "paper",
        "product_type": "SUSDT-FUTURES",
        "symbol": "BTCUSDT",
        "payload": payload or {"action": "HOLD"},
    }


def test_schema_has_durable_tables_and_required_columns(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    with sqlite3.connect(ledger.path) as db:
        tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
        assert {"events", "cycles", "orders", "fills", "positions", "protection", "reconciliation", "runtime_state"} <= tables
        for table in tables - {"sqlite_sequence"}:
            cols = {r[1] for r in db.execute(f"pragma table_info({table})")}
            assert {"cycle_id", "trace_id", "created_ms", "mode", "product_type", "symbol", "payload_hash", "schema_version"} <= cols


def test_existing_database_is_migrated_with_new_columns(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("create table cycles (cycle_id text primary key, terminal_status text, created_ms integer not null)")
    EventLedger(path)
    with sqlite3.connect(path) as db:
        cols = {r[1] for r in db.execute("pragma table_info(cycles)")}
    assert "trace_id" in cols and "schema_version" in cols


def test_cycle_and_order_identity_are_idempotent(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    assert ledger.claim_cycle("c1") is True
    assert ledger.claim_cycle("c1") is False
    ledger.record_order(event("c1", client_order_id="co-1", venue_order_id="vo-1"))
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record_order(event("c2", client_order_id="co-1"))


def test_reopen_preserves_typed_event_and_related_rows(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = EventLedger(path)
    ledger.claim_cycle("c1", trace_id="t1", mode="paper", product_type="SUSDT-FUTURES", symbol="BTCUSDT")
    ledger.append_event(event("c1", "ORDER_SUBMITTED", client_order_id="co-1"))
    ledger.record_fill(event("c1", "FILL_OBSERVED", fill_id="fill-1", client_order_id="co-1"))
    reopened = EventLedger(path)
    assert reopened.recent_events()[0]["event_type"] == "ORDER_SUBMITTED"
    assert reopened.table_rows("fills")[0]["fill_id"] == "fill-1"
