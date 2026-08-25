"""Durable, offline autonomous paper vertical slice."""
from __future__ import annotations
from src.agent.context import PortfolioView
from src.agent.cycle import run_cycle
from src.agentic_engine import Policy
from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.market.models import MarketSnapshot
from src.providers.ports import AgentProvider
from src.reconcile.engine import reconcile_positions, verify_protection
from src.policy.sizing import size_for_risk

class PaperLoop:
    def __init__(self, provider: AgentProvider, policy: Policy, ledger: EventLedger, venue: FakeExchange | None=None):
        self.provider=provider; self.policy=policy; self.ledger=ledger; self.venue=venue or FakeExchange()
    async def process(self, snapshot: MarketSnapshot, portfolio: PortfolioView, now_ts_ms: int, attach_protection: bool=True) -> dict:
        cycle_id=snapshot.snapshot_hash or snapshot.computed_hash()
        if not self.ledger.claim_cycle(cycle_id):
            self.ledger.append('CYCLE_TERMINAL', {'cycle_id':cycle_id,'disposition':'SKIPPED','reason':'DUPLICATE_CYCLE'})
            return {'status':'SKIPPED','reason':'DUPLICATE_CYCLE','cycle_id':cycle_id}
        self.ledger.append('MARKET_OBSERVED', {'cycle_id':cycle_id,'symbol':snapshot.symbol,'snapshot_hash':snapshot.snapshot_hash})
        result=await run_cycle(self.provider,snapshot,portfolio,self.policy,now_ts_ms)
        self.ledger.append('AGENT_CONTEXT_BUILT', {'cycle_id':cycle_id,'context_id':result.context_id})
        if result.decision is not None:
            self.ledger.append('AGENT_DECISION', {'cycle_id':cycle_id,'action':result.decision.action.value,'symbol':result.decision.symbol,'side':result.decision.side})
        if result.status!='APPROVED':
            disposition='HELD' if result.reason=='HOLD' else 'PARKED' if result.status=='PARKED' else 'REJECTED'
            self.ledger.append('DECISION_REJECTED' if disposition=='REJECTED' else 'CYCLE_TERMINAL', {'cycle_id':cycle_id,'disposition':disposition,'reason':result.reason})
            self.ledger.set_terminal(cycle_id,disposition)
            return {'status':disposition,'reason':result.reason,'cycle_id':cycle_id}
        d=result.decision
        if d.action.value!='ENTER':
            self.ledger.append('CYCLE_TERMINAL', {'cycle_id':cycle_id,'disposition':'HELD','reason':d.action.value})
            self.ledger.set_terminal(cycle_id,'HELD')
            return {'status':'HELD','reason':d.action.value,'cycle_id':cycle_id}
        sizing=size_for_risk(side=d.side, entry=d.entry, stop_loss=d.stop_loss,
                             requested_risk_usd=self.policy.requested_risk_usd,
                             min_notional_usd=max(self.policy.min_notional_usd, self.venue.venue.minimum_notional),
                             max_notional_usd=min(self.policy.max_position_notional_usd, d.max_notional_usd),
                             quantity_step=max(self.policy.quantity_step, self.venue.venue.quantity_step),
                             contract_multiplier=self.policy.contract_multiplier,
                             available_equity_usd=self.policy.available_equity_usd,
                             existing_gross_notional_usd=sum(p.quantity*p.entry_price*self.venue.venue.contract_multiplier for p in self.venue.positions.values()),
                             max_total_notional_usd=self.policy.max_total_notional_usd)
        oid='paper-'+cycle_id[:24]
        fill=self.venue.place_order(oid,d.symbol,d.side,sizing.quantity,d.entry)
        self.ledger.append('INTENT_APPROVED', {'cycle_id':cycle_id,'client_order_id':oid})
        self.ledger.append('ORDER_SUBMITTED', {'cycle_id':cycle_id,'client_order_id':oid})
        self.ledger.append('FILL_OBSERVED', {'cycle_id':cycle_id,'client_order_id':oid,'symbol':d.symbol,'side':d.side,'quantity':fill.quantity,'price':fill.price,'fee':fill.fee})
        if attach_protection:
            self.venue.set_protection(d.symbol,d.stop_loss,d.take_profit)
        pos=self.venue.positions[d.symbol]
        ok,reason=verify_protection({'symbol':pos.symbol,'quantity':pos.quantity,'stop_loss':pos.stop_loss,'take_profit':pos.take_profit})
        self.ledger.append('PROTECTION_VERIFIED' if ok else 'PROTECTION_FAILED', {'cycle_id':cycle_id,'status':reason})
        local={d.symbol:{'quantity':pos.quantity,'side':pos.side}}
        venue={d.symbol:{'quantity':pos.quantity,'side':pos.side}}
        rec=reconcile_positions(local,venue)
        self.ledger.append('POSITION_RECONCILED', {'cycle_id':cycle_id,'in_sync':rec.in_sync,'reasons':rec.reasons})
        disposition='EXECUTED' if ok and rec.in_sync else 'DEGRADED'
        self.ledger.append('CYCLE_TERMINAL', {'cycle_id':cycle_id,'disposition':disposition})
        self.ledger.set_terminal(cycle_id,disposition)
        return {'status':disposition,'cycle_id':cycle_id,'protection':reason,'reconciled':rec.in_sync}
