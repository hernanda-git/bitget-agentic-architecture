from src.ledger.sqlite import EventLedger
from tests.test_ledger_schema import event


def test_ledger_summaries_are_derived_from_durable_rows(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    ledger.claim_cycle("c1", trace_id="t1", mode="paper", product_type="SUSDT-FUTURES", symbol="BTCUSDT")
    ledger.append_event(event("c1", "AGENT_DECISION", action="ENTER", disposition="APPROVED"))
    ledger.append_event(event("c1", "INTENT_APPROVED", action="ENTER", disposition="APPROVED"))
    ledger.record_order(event("c1", "ORDER_SUBMITTED", client_order_id="co-1", venue_order_id="vo-1", side="BUY", status="OPEN"))
    ledger.record_fill(event("c1", "FILL_OBSERVED", fill_id="f-1", client_order_id="co-1", side="BUY", quantity=1, price=100))
    ledger.record_position(event("c1", position_id="p-1", side="LONG", quantity=1, status="OPEN"))
    ledger.record_protection(event("c1", status="PROTECTED"))
    ledger.record_reconciliation(event("c1", status="SYNC"))
    ledger.set_terminal("c1", "COMPLETED")

    assert ledger.latest_cycle()["cycle_id"] == "c1"
    assert ledger.disposition_counts()["APPROVED"] == 2
    assert ledger.open_positions()[0]["position_id"] == "p-1"
    assert ledger.latest_protection_status()["status"] == "PROTECTED"
    assert ledger.latest_reconciliation_status()["status"] == "SYNC"
    assert len(ledger.recent_events(limit=2)) == 2
    status = ledger.runtime_status()
    assert status["latest_cycle"]["cycle_id"] == "c1"
    assert status["open_positions"]


def test_summary_empty_ledger_is_safe(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    assert ledger.latest_cycle() is None
    assert ledger.disposition_counts() == {}
    assert ledger.open_positions() == []
    assert ledger.latest_protection_status() is None
    assert ledger.latest_reconciliation_status() is None
    assert ledger.recent_events() == []
