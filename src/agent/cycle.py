"""One bounded autonomous decision cycle with no execution side effects."""
from __future__ import annotations

from dataclasses import dataclass

from src.agent.context import PortfolioView, build_context
from src.agentic_engine import AgentDecision, MarketSnapshot as PolicyMarketSnapshot, Policy, validate_decision
from src.decision_parser import DecisionParseError, parse_decision
from src.market.freshness import check_freshness
from src.market.models import MarketSnapshot
from src.providers.ports import AgentProvider


@dataclass(frozen=True)
class CycleResult:
    status: str
    reason: str
    context_id: str
    decision: AgentDecision | None = None


async def run_cycle(provider: AgentProvider, snapshot: MarketSnapshot, portfolio: PortfolioView,
                    policy: Policy, now_ts_ms: int) -> CycleResult:
    freshness = check_freshness(snapshot, now_ts_ms, policy.max_snapshot_age_seconds)
    if not freshness.ok:
        return CycleResult("PARKED", freshness.reason, "")
    context = build_context(snapshot, portfolio, {
        "allow_symbols": sorted(policy.allow_symbols),
        "max_leverage": policy.max_leverage,
        "max_position_notional_usd": policy.max_position_notional_usd,
        "max_spread_bps": policy.max_spread_bps,
        "kill_switch": policy.kill_switch,
    })
    response = await provider.decide(context)
    if response.status != "OK":
        return CycleResult("NO_DECISION", response.error_code or response.status, context.context_id)
    try:
        decision = parse_decision(response.content, now_ts_ms)
    except DecisionParseError as exc:
        return CycleResult("NO_DECISION", f"DECISION_PARSE:{exc}", context.context_id)
    policy_market = PolicyMarketSnapshot(snapshot.symbol, snapshot.mark_price, snapshot.bid,
                                         snapshot.ask, (now_ts_ms - snapshot.observed_ts_ms) / 1000,
                                         snapshot.spread_bps)
    approved, reason = validate_decision(decision, policy_market, policy)
    return CycleResult("APPROVED" if approved else "REJECTED", reason,
                       context.context_id, decision)
