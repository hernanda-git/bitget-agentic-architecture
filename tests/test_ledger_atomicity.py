import pytest

from src.ledger.sqlite import EventLedger
from src.ledger.events import RuntimeEvent
from tests.test_ledger_schema import event


def test_fault_after_event_insert_rolls_back_event_and_projection(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    with pytest.raises(RuntimeError, match="injected"):
        ledger.append_event_with_projection(
            RuntimeEvent.from_dict(event("c1", "ORDER_SUBMITTED", client_order_id="co-1")),
            "orders",
            {"client_order_id": "co-1"},
            fault_injector=lambda: (_ for _ in ()).throw(RuntimeError("injected")),
        )
    assert ledger.all() == []
    assert ledger.table_rows("orders") == []


def test_projection_constraint_failure_rolls_back_event(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    with pytest.raises(KeyError):
        ledger.append_event_with_projection(RuntimeEvent.from_dict(event("c1")), "positions", {}, None)
    assert ledger.all() == []
    assert ledger.table_rows("positions") == []
