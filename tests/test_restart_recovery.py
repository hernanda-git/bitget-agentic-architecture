from src.reconcile.restart import recover_before_new_entries

def test_restart_recovery_parks_on_drift():
    result=recover_before_new_entries({'BTCUSDT':{'quantity':1}}, {'BTCUSDT':{'quantity':2}})
    assert result['status']=='PARKED'

def test_restart_recovery_allows_synced_state():
    assert recover_before_new_entries({'BTCUSDT':{'quantity':1}}, {'BTCUSDT':{'quantity':1}})=={'status':'READY'}
