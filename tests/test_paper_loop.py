import asyncio
from src.agent.context import PortfolioView
from src.agentic_engine import Policy
from src.ledger.sqlite import EventLedger
from src.market.models import Candle, MarketSnapshot
from src.paper_loop import PaperLoop
from src.providers.fake import FakeProvider
from src.providers.ports import ProviderResponse

def snap(ts=10000):
 return MarketSnapshot('BTCUSDT',100,99.9,100.1,0,10,ts,ts,(Candle('1m',99,101,98,100,10,ts),)).with_hash()
def resp(action='ENTER'):
 return ProviderResponse('OK', '{"decision_id":"decision-1234","action":"%s","symbol":"BTCUSDT","side":"BUY","entry":100,"stop_loss":95,"take_profit":110,"leverage":1,"max_notional_usd":20,"valid_until_ms":20000,"thesis":"test","invalidation":"stop"}'%action)
def policy(): return Policy(frozenset({'BTCUSDT'}),3,25,20,3,kill_switch=False)

def test_paper_loop_complete_trace(tmp_path):
 ledger=EventLedger(tmp_path/'x.sqlite3'); loop=PaperLoop(FakeProvider([resp()]),policy(),ledger)
 result=asyncio.run(loop.process(snap(),PortfolioView(),10500))
 assert result['status']=='EXECUTED'
 assert [e['event_type'] for e in ledger.all()] == ['MARKET_OBSERVED','AGENT_CONTEXT_BUILT','AGENT_DECISION','INTENT_APPROVED','ORDER_SUBMITTED','FILL_OBSERVED','PROTECTION_VERIFIED','POSITION_RECONCILED','CYCLE_TERMINAL']

def test_duplicate_survives_reopen(tmp_path):
 path=tmp_path/'x.sqlite3'; ledger=EventLedger(path); loop=PaperLoop(FakeProvider([resp()]),policy(),ledger)
 first=asyncio.run(loop.process(snap(),PortfolioView(),10500)); second=asyncio.run(PaperLoop(FakeProvider([resp()]),policy(),EventLedger(path)).process(snap(),PortfolioView(),10500))
 assert first['status']=='EXECUTED' and second['reason']=='DUPLICATE_CYCLE'

def test_missing_protection_is_degraded(tmp_path):
 ledger=EventLedger(tmp_path/'x.sqlite3'); result=asyncio.run(PaperLoop(FakeProvider([resp()]),policy(),ledger).process(snap(),PortfolioView(),10500,attach_protection=False))
 assert result['status']=='DEGRADED'
 assert any(e['event_type']=='PROTECTION_FAILED' for e in ledger.all())

def test_hold_has_no_order(tmp_path):
 ledger=EventLedger(tmp_path/'x.sqlite3'); result=asyncio.run(PaperLoop(FakeProvider([resp('HOLD')]),policy(),ledger).process(snap(),PortfolioView(),10500))
 assert result['status']=='HELD'
 assert not any(e['event_type']=='ORDER_SUBMITTED' for e in ledger.all())
