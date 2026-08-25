from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Iterable
from src.execution.fake_exchange import CloseReason, FakeExchange, OrderRequest
from src.simulation.events import MarketEvent
from src.strategies.base import CostAssumptions
from src.strategies.mean_reversion import generate_mean_reversion
from src.strategies.regime import Regime, classify_regime
from src.strategies.trend_continuation import generate_trend_continuation
from src.strategies.volatility_breakout import generate_volatility_breakout

@dataclass(frozen=True)
class BaselineConfig:
    quantity: float = 1.0
    fee_bps: float = 5.0
    funding_bps: float = 2.0
    slippage_bps: float = 2.0
    train_fraction: float = 0.6
    embargo: int = 1

@dataclass(frozen=True)
class BaselineResult:
    snapshots: int
    network_calls: int
    signed_calls: int
    orders: int
    closed_trades: int
    open_positions: int
    end_of_replay_closes: int
    fees: float
    slippage: float
    funding: float
    net_pnl: float
    strategy_breakdown: dict[str, dict]
    regime_breakdown: dict[str, dict]
    walk_forward_splits: tuple[dict, ...]
    promotion_allowed: bool
    promotion_reason: str
    replay_hash: str


def _splits(n: int, fraction: float, embargo: int) -> tuple[dict, ...]:
    cut = max(1, int(n * fraction))
    if cut >= n: return ()
    return ({"train_start": 0, "train_end": cut - 1, "test_start": min(n, cut + embargo), "test_end": n - 1},)

def _empty(): return {"closed_trades": 0, "fees": 0.0, "slippage": 0.0, "funding": 0.0, "net_pnl": 0.0}

def run_baseline(snapshots: Iterable, config: BaselineConfig = BaselineConfig()) -> BaselineResult:
    snapshots = tuple(snapshots)
    costs = CostAssumptions(config.fee_bps, config.funding_bps, config.slippage_bps)
    generators = (("trend_continuation", generate_trend_continuation), ("mean_reversion", generate_mean_reversion), ("volatility_breakout", generate_volatility_breakout))
    strategy = {name: _empty() for name, _ in generators}; regime = {r.value: _empty() for r in Regime}
    total_fees = total_slippage = total_funding = total_net = 0.0; closed = orders = end_of_replay_closes = 0
    replay_parts = []
    for index, snapshot in enumerate(snapshots):
        replay_parts.append(snapshot.snapshot_hash or snapshot.computed_hash())
        for name, generator in generators:
            venue = FakeExchange(fee_bps=config.fee_bps, slippage_bps=config.slippage_bps)
            candidates = generator(snapshot, costs)
            if not candidates: continue
            candidate = candidates[0]
            venue.market_prices[snapshot.symbol] = (snapshot.bid, snapshot.ask, snapshot.mark_price)
            oid = f"baseline-{name}-{index}"
            order = venue.submit_order(OrderRequest(oid, snapshot.symbol, candidate.side, config.quantity, None))
            if not order.filled_quantity: continue
            orders += 1
            venue.set_protection(snapshot.symbol, candidate.stop_loss, candidate.take_profit)
            for future_index, future in enumerate(snapshots[index + 1:], index + 1):
                venue.apply_market_event(MarketEvent(future.symbol, future.bid, future.ask, future.mark_price, future_index, future.source_ts_ms, future.funding_rate or 0.0))
                if not venue.read_positions(snapshot.symbol): break
            if venue.read_positions(snapshot.symbol):
                final = snapshots[-1]
                close = venue.close_position_at_end_of_replay(snapshot.symbol, final.mark_price,
                                                               f"baseline-end-of-replay-{name}-{index}")
                if not close.filled_quantity or venue.read_positions(snapshot.symbol):
                    raise RuntimeError("END_OF_REPLAY close failed to flatten paper position")
                orders += 1; end_of_replay_closes += 1
            trades = venue.closed_trades
            if not trades: continue
            trade = trades[-1]
            # FakeExchange supplies closed-trade fees and gross PnL. Funding is charged
            # deterministically over the holding events and included in net PnL.
            funding = venue.read_balance()["funding_paid"] + venue.read_balance()["funding_received"]
            slippage = sum(fill.slippage_cost for fill in venue.fills)
            total_fees += trade["entry_fee"] + trade["exit_fee"]; total_slippage += slippage; total_funding += funding
            total_net += trade["net_pnl"] - funding; closed += 1
            row = strategy[name]; row["closed_trades"] += 1; row["fees"] += trade["entry_fee"] + trade["exit_fee"]; row["slippage"] += slippage; row["funding"] += funding; row["net_pnl"] += trade["net_pnl"] - funding
            regime_name = classify_regime(snapshot).value; rr = regime[regime_name]; rr["closed_trades"] += 1; rr["fees"] += trade["entry_fee"] + trade["exit_fee"]; rr["slippage"] += slippage; rr["net_pnl"] += trade["net_pnl"] - funding
    import hashlib, json
    replay_hash = hashlib.sha256(json.dumps(replay_parts, separators=(",", ":")).encode()).hexdigest()
    splits = _splits(len(snapshots), config.train_fraction, config.embargo)
    reason = "POSITIVE_EVIDENCE_REQUIRED"
    if closed == 0: reason = "INCONCLUSIVE_NO_CLOSED_TRADES"
    elif total_net < 0: reason = "NEGATIVE_NET_PNL"
    return BaselineResult(len(snapshots), 0, 0, orders, closed, 0, end_of_replay_closes, total_fees, total_slippage, total_funding, total_net,
                          strategy, regime, splits, False, reason, replay_hash)
