from src.reconcile.restart import recover_before_new_entries
from src.execution.fake_exchange import FakeExchange, OrderRequest, OrderStatus
import pytest

def test_restart_recovery_parks_on_drift():
    result=recover_before_new_entries({'BTCUSDT':{'quantity':1}}, {'BTCUSDT':{'quantity':2}})
    assert result['status']=='PARKED'

def test_restart_recovery_allows_synced_state():
    assert recover_before_new_entries({'BTCUSDT':{'quantity':1}}, {'BTCUSDT':{'quantity':1}})=={'status':'READY'}


def test_restart_recovery_reports_interrupted_cycles_as_recoverable():
    result = recover_before_new_entries({}, {}, interrupted_cycles=["cycle-1"])
    assert result["status"] == "READY"
    assert result["interrupted_cycles"]["cycle-1"] == "RECOVERABLE"


@pytest.mark.parametrize("stage", ["observation", "decision", "intent", "order_ack"])
def test_restart_recovery_covers_crash_boundaries(stage):
    result = recover_before_new_entries({}, {}, interrupted_cycles=[f"cycle-after-{stage}"])
    assert result["status"] == "READY"
    assert result["interrupted_cycles"][f"cycle-after-{stage}"] == "RECOVERABLE"


def test_fake_exchange_duplicate_client_id_is_idempotent():
    exchange = FakeExchange()
    request = OrderRequest("client-1", "BTCUSDT", "BUY", 1, None)
    first = exchange.submit_order(request)
    second = exchange.submit_order(request)
    assert first == second
    assert len(exchange.orders) == 1


def test_restart_recovery_parks_on_kill_switch_and_provider_outage():
    assert recover_before_new_entries({}, {}, kill_switch=True)["status"] == "PARKED"
    assert recover_before_new_entries({}, {}, provider_available=False)["status"] == "PARKED"
