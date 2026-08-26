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
    real_funding: bool = False
    min_edge_coverage: float = 1.0

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
    spread: float
    slippage: float
    funding: float
    gross_pnl: float
    net_pnl: float
    strategy_breakdown: dict[str, dict]
    regime_breakdown: dict[str, dict]
    walk_forward_splits: tuple[dict, ...]
    cost_gate_skipped: int = 0
    promotion_allowed: bool = False
    promotion_reason: str = ""
    replay_hash: str = ""
    trade_pnls: tuple[float, ...] = ()


def _splits(n: int, fraction: float, embargo: int) -> tuple[dict, ...]:
    cut = max(1, int(n * fraction))
    if cut >= n: return ()
    return ({"train_start": 0, "train_end": cut - 1, "test_start": min(n, cut + embargo), "test_end": n - 1},)

def _empty(): return {"closed_trades": 0, "gross_pnl": 0.0, "fees": 0.0, "spread": 0.0, "slippage": 0.0, "funding": 0.0, "net_pnl": 0.0}

# Canonical strategy registry. Kept explicit so attribution, walk-forward, and
# the combined baseline always enumerate strategies in the same order.
ALL_STRATEGIES = (
    ("trend_continuation", generate_trend_continuation),
    ("mean_reversion", generate_mean_reversion),
    ("volatility_breakout", generate_volatility_breakout),
)

def _replay_funding_rate(snapshot, funding_bps: float) -> float:
    """Apply the configured stress rate while preserving fixture funding direction."""
    raw_rate = snapshot.funding_rate or 0.0
    if not raw_rate:
        return 0.0
    return (1 if raw_rate > 0 else -1) * funding_bps / 10_000

def _funding_cost(balance: dict) -> float:
    """Return net funding paid, with funding received treated as a credit."""
    return balance["funding_paid"] - balance["funding_received"]

def _validate_replay_snapshots(snapshots: tuple) -> None:
    """Reject replay data whose identity or ordering cannot be trusted."""
    if not snapshots:
        return
    symbol = snapshots[0].symbol
    previous_observed = previous_source = None
    for index, snapshot in enumerate(snapshots):
        if not snapshot.snapshot_hash or snapshot.snapshot_hash != snapshot.computed_hash():
            raise ValueError(f"evaluation data snapshot hash mismatch at index {index}")
        if snapshot.symbol != symbol:
            raise ValueError(f"evaluation data symbol mismatch at index {index}")
        if previous_observed is not None and snapshot.observed_ts_ms < previous_observed:
            raise ValueError(f"evaluation data timestamp regression at index {index}")
        if previous_source is not None and snapshot.source_ts_ms < previous_source:
            raise ValueError(f"evaluation data timestamp regression at index {index}")
        for label, candles in (("candles", snapshot.candles), *snapshot.candles_by_window.items()):
            previous_candle_ts = None
            for candle in candles:
                if previous_candle_ts is not None and candle.source_ts_ms < previous_candle_ts:
                    raise ValueError(
                        f"evaluation data candle timestamp regression at index {index} in {label}"
                    )
                previous_candle_ts = candle.source_ts_ms
        previous_observed = snapshot.observed_ts_ms
        previous_source = snapshot.source_ts_ms

def run_baseline(snapshots: Iterable, config: BaselineConfig = BaselineConfig(), *,
                 evaluation_start: int = 0, evaluation_end: int | None = None,
                 strategies=None) -> BaselineResult:
    snapshots = tuple(snapshots)
    _validate_replay_snapshots(snapshots)
    if not isinstance(config.min_edge_coverage, (int, float)) or not math.isfinite(config.min_edge_coverage) or config.min_edge_coverage < 1.0:
        raise ValueError("min_edge_coverage must be a finite number greater than or equal to 1.0")
    if evaluation_end is None:
        evaluation_end = len(snapshots) - 1
    if not snapshots or not 0 <= evaluation_start <= evaluation_end < len(snapshots):
        raise ValueError("evaluation window must be within snapshots")
    costs = CostAssumptions(config.fee_bps, config.funding_bps, config.slippage_bps)
    generators = strategies if strategies is not None else ALL_STRATEGIES
    strategy = {name: _empty() for name, _ in generators}; regime = {r.value: _empty() for r in Regime}
    total_fees = total_spread = total_slippage = total_funding = total_gross = 0.0; closed = orders = end_of_replay_closes = protection_attachments = 0
    reconciliation_checks = 0
    cost_gate_skipped = 0
    # One open position per strategy: a real bot cannot stack overlapping
    # entries, so a strategy is blocked from re-entering until its previous
    # position has actually closed (including the bar the exit filled on).
    busy_until: dict[str, int] = {}
    replay_parts = []
    trade_pnls: list[float] = []
    for index, snapshot in enumerate(snapshots):
        if index < evaluation_start or index > evaluation_end:
            continue
        replay_parts.append(snapshot.snapshot_hash or snapshot.computed_hash())
        for name, generator in generators:
            if index <= busy_until.get(name, -1):
                continue
            venue = FakeExchange(fee_bps=config.fee_bps, slippage_bps=config.slippage_bps)
            candidates = generator(snapshot, costs)
            if not candidates: continue
            candidate = candidates[0]
            if candidate.expected_move < config.min_edge_coverage * candidate.expected_cost:
                cost_gate_skipped += 1
                continue
            venue.market_prices[snapshot.symbol] = (snapshot.bid, snapshot.ask, snapshot.mark_price)
            oid = f"baseline-{name}-{index}"
            order = venue.submit_order(OrderRequest(oid, snapshot.symbol, candidate.side, config.quantity, None))
            if not order.filled_quantity: continue
            orders += 1
            venue.set_protection(snapshot.symbol, candidate.stop_loss, candidate.take_profit)
            protection_attachments += 1
            close_index = evaluation_end
            for future_index, future in enumerate(snapshots[index + 1:evaluation_end + 1], index + 1):
                future_funding = future.funding_rate if (config.real_funding and future.funding_rate is not None) else _replay_funding_rate(future, config.funding_bps)
                venue.apply_market_event(MarketEvent(future.symbol, future.bid, future.ask, future.mark_price, future_index, future.source_ts_ms, future_funding))
                if not venue.read_positions(snapshot.symbol):
                    close_index = future_index
                    break
            busy_until[name] = max(close_index, index)
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
            spread = trade["spread_cost"]
            slippage = trade["slippage_cost"]
            total_fees += trade["entry_fee"] + trade["exit_fee"]; total_spread += spread; total_slippage += slippage; total_funding += funding
            total_gross += trade["gross_pnl"]; closed += 1
            trade_pnls.append(trade["gross_pnl"] - trade["entry_fee"] - trade["exit_fee"] - spread - slippage - funding)
            row = strategy[name]; row["closed_trades"] += 1; row["gross_pnl"] += trade["gross_pnl"]; row["fees"] += trade["entry_fee"] + trade["exit_fee"]; row["spread"] += spread; row["slippage"] += slippage; row["funding"] += funding
            row["net_pnl"] = row["gross_pnl"] - row["fees"] - row["spread"] - row["slippage"] - row["funding"]
            regime_name = classify_regime(snapshot).value; rr = regime[regime_name]; rr["closed_trades"] += 1; rr["gross_pnl"] += trade["gross_pnl"]; rr["fees"] += trade["entry_fee"] + trade["exit_fee"]; rr["spread"] += spread; rr["slippage"] += slippage; rr["funding"] += funding; rr["net_pnl"] = rr["gross_pnl"] - rr["fees"] - rr["spread"] - rr["slippage"] - rr["funding"]
    import hashlib, json
    replay_hash = hashlib.sha256(json.dumps(replay_parts, separators=(",", ":")).encode()).hexdigest()
    splits = _splits(len(snapshots), config.train_fraction, config.embargo) if evaluation_start == 0 and evaluation_end == len(snapshots) - 1 else ()
    total_net = total_gross - total_fees - total_spread - total_slippage - total_funding
    reason = "POSITIVE_EVIDENCE_REQUIRED"
    if closed == 0: reason = "INCONCLUSIVE_NO_CLOSED_TRADES"
    elif total_net < 0: reason = "NEGATIVE_NET_PNL"
    return BaselineResult(len(snapshots), 0, 0, orders, closed, 0, end_of_replay_closes,
                          protection_attachments, reconciliation_checks, total_fees, total_spread, total_slippage, total_funding, total_gross, total_net,
                          strategy, regime, splits,
                          cost_gate_skipped=cost_gate_skipped,
                          promotion_allowed=False, promotion_reason=reason, replay_hash=replay_hash,
                          trade_pnls=tuple(trade_pnls))


def run_walk_forward(snapshots: Iterable, config: BaselineConfig = BaselineConfig(),
                     *, strategies=None) -> tuple[dict, ...]:
    """Evaluate non-overlapping test windows after an expanding train period and embargo.

    When ``strategies`` is given (a sequence of ``(name, generator)`` pairs), only
    those strategies are replayed, so the result isolates their signal. Defaults
    to all canonical strategies.
    """
    if not 0 < config.train_fraction < 1 or config.embargo < 0 or config.test_window < 1:
        raise ValueError("walk-forward parameters must have 0 < train_fraction < 1, embargo >= 0, and test_window >= 1")
    snapshots = tuple(snapshots)
    _validate_replay_snapshots(snapshots)
    if not snapshots:
        raise ValueError("walk-forward requires snapshots")
    cut = max(1, int(len(snapshots) * config.train_fraction))
    window = config.test_window
    rows = []
    test_start = cut + config.embargo
    while test_start + window <= len(snapshots):
        test_end = test_start + window - 1
        # Keep all pre-test snapshots available as feature context, but only
        # execute and flatten positions inside this test window. This avoids
        # cold-start indicators and prevents future test windows leaking into
        # the current result.
        result = run_baseline(snapshots, replace(config, train_fraction=0.5),
                              evaluation_start=test_start, evaluation_end=test_end,
                              strategies=strategies)
        rows.append({"train_start": 0, "train_end": test_start - config.embargo - 1,
                     "test_start": test_start, "test_end": test_end,
                     "context_start": 0, "context_end": test_start - 1,
                     "test_snapshots": test_end - test_start + 1,
                     "closed_trades": result.closed_trades, "gross_pnl": result.gross_pnl,
                     "protection_attachments": result.protection_attachments,
                     "reconciliation_checks": result.reconciliation_checks,
                     "fees": result.fees, "funding": result.funding, "slippage": result.slippage, "net_pnl": result.net_pnl,
                     "spread": result.spread,
                     "strategy_breakdown": result.strategy_breakdown})
        test_start = test_end + 1 + config.embargo
    if not any(row["test_snapshots"] == window for row in rows):
        raise ValueError("walk-forward requires at least one complete test window")
    return tuple(rows)


def summarize_walk_forward(rows: Iterable[dict]) -> dict:
    """Aggregate walk-forward windows into robustness facts (fail closed on empty input)."""
    rows = tuple(rows)
    if not rows:
        raise ValueError("walk-forward summary requires at least one window row")
    net_values = [row["net_pnl"] for row in rows]
    return {
        "windows": len(rows),
        "windows_with_trades": sum(1 for row in rows if row["closed_trades"] > 0),
        "profitable_windows": sum(1 for value in net_values if value > 0),
        "closed_trades": sum(row["closed_trades"] for row in rows),
        "total_net_pnl": sum(net_values),
        "worst_window_net_pnl": min(net_values),
        "best_window_net_pnl": max(net_values),
    }


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
                     "spread": result.spread, "slippage": result.slippage, "funding": result.funding,
                     "net_pnl": result.net_pnl})
    return tuple(rows)


def run_coverage_variants(snapshots: Iterable, config: BaselineConfig = BaselineConfig(),
                          coverages=(1.0, 2.0, 3.0)) -> tuple[dict, ...]:
    """Run the same replay under increasing minimum edge-coverage requirements.

    Each row reports the raw cost-inclusive outcome for that coverage level.
    This is measurement, not tuning: no variant changes the promotion gate.
    """
    coverages = tuple(coverages)
    if not coverages or any(not isinstance(c, (int, float)) or not math.isfinite(c) or c < 1.0 for c in coverages):
        raise ValueError("coverage levels must be finite numbers greater than or equal to 1.0")
    rows = []
    for coverage in coverages:
        result = run_baseline(snapshots, replace(config, min_edge_coverage=float(coverage)))
        rows.append({"min_edge_coverage": float(coverage),
                     "orders": result.orders, "closed_trades": result.closed_trades,
                     "gross_pnl": result.gross_pnl, "fees": result.fees,
                     "spread": result.spread, "slippage": result.slippage, "funding": result.funding,
                     "net_pnl": result.net_pnl, "cost_gate_skipped": result.cost_gate_skipped,
                     "promotion_reason": result.promotion_reason})
    return tuple(rows)


def run_strategy_attribution(snapshots: Iterable, config: BaselineConfig = BaselineConfig()) -> dict:
    """Independent per-strategy walk-forward attribution (measurement only).

    Each canonical strategy is replayed ALONE across the same walk-forward
    windows so its signal can be attributed without the other strategies' trades
    masking or inflating it. This is measurement, never selection:

    - No strategy is selected, ranked, or promoted to a "winner" role.
    - The test set is never used to pick a strategy (no walk-forward peeking).
    - ``selection_blocked`` is always True and no ``best``/``selected``/
      ``promoted`` key is emitted.

    The deterministic promotion gate (NEGATIVE_NET_PNL) remains the only thing
    that may unblock Phase 6; this function never influences it.
    """
    snapshots = tuple(snapshots)
    if not snapshots:
        raise ValueError("strategy attribution requires snapshots")
    _validate_replay_snapshots(snapshots)
    out: dict = {}
    for name, generator in ALL_STRATEGIES:
        wf = run_walk_forward(snapshots, config, strategies=((name, generator),))
        summary = summarize_walk_forward(wf)
        out[name] = {
            "windows": summary["windows"],
            "windows_with_trades": summary["windows_with_trades"],
            "profitable_windows": summary["profitable_windows"],
            "closed_trades": summary["closed_trades"],
            "total_net_pnl": summary["total_net_pnl"],
            "worst_window_net_pnl": summary["worst_window_net_pnl"],
            "best_window_net_pnl": summary["best_window_net_pnl"],
            "windows_net_pnl": [round(row["net_pnl"], 6) for row in wf],
        }
    out["selection_blocked"] = True
    out["strategies_evaluated"] = [name for name, _ in ALL_STRATEGIES]
    return out
