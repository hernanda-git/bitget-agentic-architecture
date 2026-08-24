from src.reconcile.engine import reconcile_positions, verify_protection


def test_reconcile_detects_drift():
    result=reconcile_positions({'BTCUSDT':{'quantity':1}}, {'BTCUSDT':{'quantity':2}})
    assert result.in_sync is False
    assert 'POSITION_DRIFT:BTCUSDT' in result.reasons


def test_protection_is_not_assumed():
    ok, reason=verify_protection({'symbol':'BTCUSDT','quantity':1,'stop_loss':None,'take_profit':110})
    assert (ok,reason)==(False,'STOP_LOSS_MISSING')
    assert verify_protection({'symbol':'BTCUSDT','quantity':1,'stop_loss':95,'take_profit':110})==(True,'PROTECTED')
