from src.reconcile.engine import reconcile_positions

def recover_before_new_entries(local, venue):
    result=reconcile_positions(local, venue)
    if not result.in_sync:
        return {'status':'PARKED','reason':'RECONCILIATION_DRIFT','details':result.reasons}
    return {'status':'READY'}
