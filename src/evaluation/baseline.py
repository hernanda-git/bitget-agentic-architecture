from __future__ import annotations
from dataclasses import dataclass, field, asdict, replace
import math
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
    test_window: int = 10

@dataclass(frozen=True)
class BaselineResult:
    snapshots: int
    network_calls: int
    signed_calls: int
    orders: int
    closed_trades: int
    open_positions: int
    end_of_replay_closes: int
    protection_attachments: int
    reconciliation_checks: int
    fees: float
    slippage: float
    funding: float
    gross_pnl: float
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

def _empty(): return {"closed_trades": 0, "gross_pnl": 0.0, "fees": 0.0, "slippage": 0.0, "funding": 0.0, "net_pnl": 0.0}

def _replay_funding_rate(snapshot, funding_bps: float) -> float:
    """Apply the configured stress rate while preserving fixture funding direction."""
    raw_rate = snapshot.funding_rate or 0.0
    if not raw_rate:
        return 0.0
    return (1 if raw_rate > 0 else -1) * funding_bps / 10_000

def _funding_cost(balance: dict) -> float:
    """Return net funding paid, with funding received treated as a credit."""
    return balance["funding_paid"] - balance["funding_received"]

def run_baseline(snapshots: Iterable, config: BaselineConfig = BaselineConfig(), *,
                 evaluation_start: int = 0, evaluation_end: int | None = None) -> BaselineResult:
    snapshots = tuple(snapshots)
    if evaluation_end is None:
        evaluation_end = len(snapshots) - 1
    if not snapshots or not 0 <= evaluation_start <= evaluation_end < len(snapshots):
        raise ValueError("evaluation window must be within snapshots")
    costs = CostAssumptions(config.fee_bps, config.funding_bps, config.slippage_bps)
    generators = (("trend_continuation", generate_trend_continuation), ("mean_reversion", generate_mean_reversion), ("volatility_breakout", generate_volatility_breakout))
    strategy = {name: _empty() for name, _ in generators}; regime = {r.value: _empty() for r in Regime}
    total_fees = total_slippage = total_funding = total_gross = 0.0; closed = orders = end_of_replay_closes = protection_attachments = 0
    reconciliation_checks = 0
    replay_parts = []
    for index, snapshot in enumerate(snapshots):
        if index < evaluation_start or index > evaluation_end:
            continue
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
            protection_attachments += 1
            for future_index, future in enumerate(snapshots[index + 1:evaluation_end + 1], index + 1):
                venue.apply_market_event(MarketEvent(future.symbol, future.bid, future.ask, future.mark_price, future_index, future.source_ts_ms, _replay_funding_rate(future, config.funding_bps)))
                if not venue.read_positions(snapshot.symbol): break
            if venue.read_positions(snapshot.symbol):
                final = snapshots[evaluation_end]
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
            funding = _funding_cost(venue.read_balance())
            slippage = sum(fill.slippage_cost for fill in venue.fills)
            total_fees += trade["entry_fee"] + trade["exit_fee"]; total_slippage += slippage; total_funding += funding
            total_gross += trade["gross_pnl"]; closed += 1
            row = strategy[name]; row["closed_trades"] += 1; row["gross_pnl"] += trade["gross_pnl"]; row["fees"] += trade["entry_fee"] + trade["exit_fee"]; row["slippage"] += slippage; row["funding"] += funding
            row["net_pnl"] = row["gross_pnl"] - row["fees"] - row["funding"]
            regime_name = classify_regime(snapshot).value; rr = regime[regime_name]; rr["closed_trades"] += 1; rr["gross_pnl"] += trade["gross_pnl"]; rr["fees"] += trade["entry_fee"] + trade["exit_fee"]; rr["slippage"] += slippage; rr["funding"] += funding; rr["net_pnl"] = rr["gross_pnl"] - rr["fees"] - rr["funding"]
    import hashlib, json
    replay_hash = hashlib.sha256(json.dumps(replay_parts, separators=(",", ":")).encode()).hexdigest()
    splits = _splits(len(snapshots), config.train_fraction, config.embargo) if evaluation_start == 0 and evaluation_end == len(snapshots) - 1 else ()
    total_net = total_gross - total_fees - total_funding
    reason = "POSITIVE_EVIDENCE_REQUIRED"
    if closed == 0: reason = "INCONCLUSIVE_NO_CLOSED_TRADES"
    elif total_net < 0: reason = "NEGATIVE_NET_PNL"
    return BaselineResult(len(snapshots), 0, 0, orders, closed, 0, end_of_replay_closes,
                          protection_attachments, reconciliation_checks, total_fees, total_slippage, total_funding, total_gross, total_net,
                          strategy, regime, splits, False, reason, replay_hash)


def run_walk_forward(snapshots: Iterable, config: BaselineConfig = BaselineConfig()) -> tuple[dict, ...]:
    """Evaluate non-overlapping test windows after an expanding train period and embargo."""
    if not 0 < config.train_fraction < 1 or config.embargo < 0 or config.test_window < 1:
        raise ValueError("walk-forward parameters must have 0 < train_fraction < 1, embargo >= 0, and test_window >= 1")
    snapshots = tuple(snapshots)
    if not snapshots:
        raise ValueError("walk-forward requires snapshots")
    cut = max(1, int(len(snapshots) * config.train_fraction))
    window = config.test_window
    rows = []
    test_start = cut + config.embargo
    while test_start < len(snapshots):
        test_end = min(len(snapshots) - 1, test_start + window - 1)
        # Keep all pre-test snapshots available as feature context, but only
        # execute and flatten positions inside this test window. This avoids
        # cold-start indicators and prevents future test windows leaking into
        # the current result.
        result = run_baseline(snapshots, replace(config, train_fraction=0.5),
                              evaluation_start=test_start, evaluation_end=test_end)
        rows.append({"train_start": 0, "train_end": test_start - config.embargo - 1,
                     "test_start": test_start, "test_end": test_end,
                     "context_start": 0, "context_end": test_start - 1,
                     "test_snapshots": test_end - test_start + 1,
                     "closed_trades": result.closed_trades, "gross_pnl": result.gross_pnl,
                     "protection_attachments": result.protection_attachments,
                     "reconciliation_checks": result.reconciliation_checks,
                     "fees": result.fees, "funding": result.funding, "net_pnl": result.net_pnl,
                     "strategy_breakdown": result.strategy_breakdown})
        test_start = test_end + 1 + config.embargo
    if not any(row["test_snapshots"] == window for row in rows):
        raise ValueError("walk-forward requires at least one complete test window")
    return tuple(rows)


def run_cost_stress(snapshots: Iterable, config: BaselineConfig = BaselineConfig(), multipliers=(1.0, 1.5, 2.0)) -> tuple[dict, ...]:
    """Run the same replay under increasingly adverse fee, funding, and slippage assumptions."""
    multipliers = tuple(multipliers)
    if not multipliers or any(not isinstance(multiplier, (int, float)) or not math.isfinite(multiplier) or multiplier <= 0 for multiplier in multipliers):
        raise ValueError("cost-stress multipliers must be finite and greater than zero")
    rows = []
    for multiplier in multipliers:
        result = run_baseline(snapshots, replace(config, fee_bps=config.fee_bps * multiplier,
                                                 funding_bps=config.funding_bps * multiplier,
                                                 slippage_bps=config.slippage_bps * multiplier))
        rows.append({"multiplier": multiplier, "fee_bps": config.fee_bps * multiplier,
                     "funding_bps": config.funding_bps * multiplier,
                     "slippage_bps": config.slippage_bps * multiplier,
                     "gross_pnl": result.gross_pnl, "fees": result.fees,
                     "funding": result.funding, "net_pnl": result.net_pnl})
    return tuple(rows)
