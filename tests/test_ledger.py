from src.ledger.sqlite import EventLedger


def test_ledger_is_append_only_and_reopenable(tmp_path):
    path=tmp_path/'events.sqlite3'
    first=EventLedger(path)
    first.append('AGENT_DECISION', {'decision_id':'d1','action':'HOLD'})
    first.append('POLICY_REJECTED', {'reason':'STALE_MARKET_DATA'})
    reopened=EventLedger(path)
    events=reopened.all()
    assert [e['event_type'] for e in events] == ['AGENT_DECISION','POLICY_REJECTED']
    assert events[0]['payload']['decision_id']=='d1'
