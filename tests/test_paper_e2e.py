from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from scripts.run_paper import run_paper_once


def test_paper_e2e_records_fill_and_protection(tmp_path):
    result=run_paper_once(FakeExchange(), EventLedger(tmp_path/'ledger.sqlite3'))
    assert result == {'status':'PAPER_FILLED','fee':0.05,'protected':True}
