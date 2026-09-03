from __future__ import annotations
from dataclasses import dataclass, field, asdict, replace
import math
from decimal import Decimal, ROUND_DOWN
from statistics import mean
from typing import Any, Iterable
from src.evaluation.statistics import bootstrap_ci
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
    # Notional cap used to DERIVE order quantity from the mark price. Mirrors the
    # live policy `max_position_notional_usd`. Disabled by default (0.0) so callers
    # that pass an explicit `quantity` keep their existing semantics; opt in by
    # setting a positive cap (the evaluation scripts set 25.0 to match live policy).
    max_position_notional_usd: float = 0.0

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
    position_notional_usd: float = 25.0


def effective_quantity(config: BaselineConfig, mark_price: float) -> float:
    """Derive the order quantity from the configured notional cap.

    Returns ``min(config.quantity, notional / mark)`` when a positive notional
    cap is configured and the mark is positive. Otherwise (cap disabled or a
    degenerate mark) it returns the configured ``quantity`` unchanged, so a
    missing/notional-agnostic config still trades a fixed size.

    Fail-closed: any degenerate input (non-positive notional, non-positive mark,
    non-finite values, a zero-division) falls back to the configured quantity
    rather than raising or emitting a nonsensical size.
    """
    if not config.max_position_notional_usd or mark_price <= 0:
        return config.quantity
    try:
        notional_qty = config.max_position_notional_usd / float(mark_price)
    except (ZeroDivisionError, TypeError, ValueError):
        return config.quantity
    if not math.isfinite(notional_qty):
        return config.quantity
    return min(config.quantity, notional_qty)


def _floor_to_step(qty: float, step: float) -> float:
    """Floor a quantity to a multiple of the venue's contract step.

    Real venues reject orders whose quantity is not an integer multiple of the
    contract step, so a notional-derived quantity must be snapped down to a
    valid size before submission. Flooring (not rounding) keeps the position
    notional at or below the configured cap.
    """
    if not step or step <= 0:
        return qty
    try:
        q = (Decimal(str(qty)) / Decimal(str(step))).to_integral_value(rounding=ROUND_DOWN)
        return float(q * Decimal(str(step)))
    except (ArithmeticError, ValueError):
        return qty


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
    notional_sum = 0.0; notional_n = 0
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
        # Size each position from the notional cap (mirrors the live policy's
        # max_position_notional_usd) so cost/reward scale to the real system
        # instead of a hardcoded 1.0 contract.
        eff_qty = effective_quantity(config, snapshot.mark_price)
        for name, generator in generators:
            if index <= busy_until.get(name, -1):
                continue
            venue = FakeExchange(fee_bps=config.fee_bps, slippage_bps=config.slippage_bps)
            # Snap the notional-derived size down to a valid contract multiple so
            # the (deterministic) venue accepts the order; never exceed the cap.
            order_qty = _floor_to_step(eff_qty, venue.venue.quantity_step)
            candidates = generator(snapshot, costs)
            if not candidates: continue
            candidate = candidates[0]
            if candidate.expected_move < config.min_edge_coverage * candidate.expected_cost:
                cost_gate_skipped += 1
                continue
            venue.market_prices[snapshot.symbol] = (snapshot.bid, snapshot.ask, snapshot.mark_price)
            oid = f"baseline-{name}-{index}"
            order = venue.submit_order(OrderRequest(oid, snapshot.symbol, candidate.side, order_qty, None))
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
            notional_sum += order_qty * snapshot.mark_price; notional_n += 1
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
                          trade_pnls=tuple(trade_pnls),
                          position_notional_usd=notional_sum / notional_n if notional_n else 0.0)


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
                     "trade_pnls": list(result.trade_pnls),
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


def gate_walk_forward_robustness(rows: Iterable[dict], *, trade_pnls=None,
                                 min_closed_trades: int = 30, confidence: float = 0.95,
                                 seed: int = 0, n_tests: int = 1) -> dict:
    """Measurement-only robustness facts over walk-forward windows.

    Reports the two promotion gates that Phase 7 marked NOT_EVIDENCED -- an
    adequate closed-trade sample and positive expectancy with a supporting
    confidence interval -- as computed, honest facts. This function NEVER
    changes the deterministic promotion gate (``NEGATIVE_NET_PNL``) and NEVER
    emits a promoted/selected/winner flag, so it stays compatible with the
    always-blocked selection policy.

    A positive-expectancy-with-CI claim requires BOTH an adequate sample AND a
    confidence-interval lower bound strictly above zero. A point estimate above
    zero with a CI straddling zero does not count, and an inadequate sample fails
    closed regardless of how profitable it looks.

    Multiple-testing correction: when this gate is one of ``n_tests``
    simultaneous candidate-edge tests (for example, the pipeline scans several
    strategies and datasets), the confidence level is Bonferroni-adjusted to
    ``1 - (1 - confidence) / n_tests``. That widens the CI so its lower bound
    must be even more strictly above zero, which makes a lone spuriously-positive
    window fail closed instead of masquerading as edge. ``n_tests == 1`` (the
    default) reproduces the original, uncorrected behavior.
    """
    rows = tuple(rows)
    if not rows:
        raise ValueError("walk-forward robustness gate requires at least one window row")
    if not isinstance(min_closed_trades, int) or min_closed_trades < 1:
        raise ValueError("min_closed_trades must be a positive integer")
    if not isinstance(n_tests, int) or n_tests < 1:
        raise ValueError("n_tests must be a positive integer")
    # Bonferroni-adjusted confidence level: one of ``n_tests`` simultaneous tests
    # keeps the family-wise error rate at (1 - confidence). This widens the CI so
    # a lone lucky positive window can no longer clear the lower bound.
    effective_confidence = 1.0 - (1.0 - confidence) / n_tests
    summary = summarize_walk_forward(rows)
    total_closed = summary["closed_trades"]
    adequate_sample = total_closed >= min_closed_trades

    window_net = [float(r["net_pnl"]) for r in rows]
    window_ci = bootstrap_ci(window_net, confidence=effective_confidence, seed=seed)

    trade_ci = None
    trade_expectancy = None
    if trade_pnls is not None:
        tp = tuple(float(v) for v in trade_pnls)
        if tp and len(tp) >= min_closed_trades:
            trade_expectancy = mean(tp)
            trade_ci = bootstrap_ci(tp, confidence=effective_confidence, seed=seed)

    if trade_ci is not None:
        expectancy_ci = trade_ci
        expectancy_mean = trade_expectancy
    else:
        expectancy_ci = window_ci
        expectancy_mean = mean(window_net) if window_net else 0.0

    # Fail closed: an inadequate sample can never prove positive expectancy, and
    # the CI lower bound must be strictly above zero (no straddling zero).
    expectancy_positive_with_ci = (
        adequate_sample and expectancy_ci[0] is not None and expectancy_ci[0] > 0
    )
    return {
        "windows": summary["windows"],
        "windows_with_trades": summary["windows_with_trades"],
        "profitable_windows": summary["profitable_windows"],
        "total_closed_trades": total_closed,
        "min_closed_trades": min_closed_trades,
        "adequate_sample": adequate_sample,
        "confidence": confidence,
        "n_tests": n_tests,
        "effective_confidence": effective_confidence,
        "expectancy_mean": expectancy_mean,
        "expectancy_ci": expectancy_ci,
        "expectancy_positive_with_ci": expectancy_positive_with_ci,
        "selection_blocked": True,
    }


def family_wise_robustness(tests: Iterable[dict], *, alpha: float = 0.05) -> dict:
    """Bonferroni multiple-testing correction across simultaneous candidate-edge tests.

    The walk-forward pipeline implicitly scans many candidate edges (3 strategies
    x 4 datasets = 12 families, often more when coverage/cost variants are added),
    so judging every candidate at the same naive 0.95 level lets a single
    spuriously-positive window masquerade as proven edge. This aggregator reports
    how many candidates would look positive under (a) the naive per-test level and
    (b) a Bonferroni-corrected family-wise level, so a lone lucky survivor cannot
    hide among a sea of negatives.

    Each candidate dict must carry ``rows`` (walk-forward window rows) and may
    carry ``trade_pnls``. A candidate is "positive" when its gate returns
    ``expectancy_positive_with_ci``. The naive verdict uses ``n_tests=1`` at the
    individual level ``1 - alpha``; the corrected verdict uses ``n_tests=len(tests)``
    at the per-test level ``1 - alpha/len(tests)``, which is exactly the
    Bonferroni adjustment implemented inside ``gate_walk_forward_robustness``.

    This is MEASUREMENT ONLY. It never changes the deterministic promotion gate
    (``NEGATIVE_NET_PNL``) and never emits a promoted/selected/winner flag, so it
    stays compatible with the always-blocked Phase 6 selection policy.
    """
    tests = tuple(tests)
    if not tests:
        raise ValueError("family-wise robustness requires at least one test")
    if not isinstance(alpha, (int, float)) or not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be a finite number strictly between 0 and 1")
    k = len(tests)
    uncorrected_positives = 0
    corrected_positives = 0
    for test in tests:
        rows = test["rows"]
        trade_pnls = test.get("trade_pnls")
        naive = gate_walk_forward_robustness(
            rows, trade_pnls=trade_pnls, n_tests=1, confidence=1.0 - alpha
        )
        corrected = gate_walk_forward_robustness(
            rows, trade_pnls=trade_pnls, n_tests=k, confidence=1.0 - alpha
        )
        if naive["expectancy_positive_with_ci"]:
            uncorrected_positives += 1
        if corrected["expectancy_positive_with_ci"]:
            corrected_positives += 1
    return {
        "tests": k,
        "correction": "bonferroni",
        "family_wise_alpha": alpha,
        "any_uncorrected_positive": uncorrected_positives > 0,
        "uncorrected_positives": uncorrected_positives,
        "any_corrected_positive": corrected_positives > 0,
        "corrected_positives": corrected_positives,
        "selection_blocked": True,
    }


def evaluate_candidate_family(candidates: Iterable, config: BaselineConfig = BaselineConfig(),
                               *, min_closed_trades: int = 30, confidence: float = 0.95,
                               seed: int = 0, resource_budget: Any = None) -> dict:
    """Measurement-only walk-forward + family-wise correction across a candidate family.

    Runs the SAME cost-inclusive, walk-forward, robustness-gated engine over each
    independent candidate dataset (e.g. several symbols) and then applies the
    Bonferroni family-wise multiple-testing correction across the whole family.

    A naive pipeline would scan many symbols and call any single spuriously
    positive window "edge". This orchestrator reports how many candidates look
    positive BEFORE versus AFTER the family-wise correction, so a lone lucky
    survivor among negatives cannot masquerade as edge.

    This is MEASUREMENT ONLY. ``selection_blocked`` is always True and no
    ``promoted``/``selected``/``winner`` key is ever emitted, so it stays
    compatible with the always-blocked Phase 6 selection policy.
    """
    candidates = tuple(candidates)
    if not candidates:
        raise ValueError("evaluate_candidate_family requires at least one candidate")
    if not isinstance(min_closed_trades, int) or min_closed_trades < 1:
        raise ValueError("min_closed_trades must be a positive integer")
    if not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("confidence must be a finite number strictly between 0 and 1")
    config = config or BaselineConfig()
    per_candidate: list[dict] = []
    tests: list[dict] = []
    # Fail closed before any heavy replay, and again before each candidate, so a
    # long family-wise scan aborts itself (never kills anything) if the host
    # drifts into memory/swap/disk/inode pressure mid-run.
    if resource_budget is not None:
        resource_budget.preflight()
    for index, (name, snapshots) in enumerate(candidates):
        if resource_budget is not None:
            resource_budget.assert_within()
        baseline = run_baseline(snapshots, config)
        wf = run_walk_forward(snapshots, config)
        # Robustness confidence intervals must use only trades closed inside
        # chronological OOS windows. Full-replay baseline.trade_pnls includes
        # train/context trades and would contaminate the OOS evidence.
        oos_trade_pnls = tuple(
            float(pnl) for row in wf for pnl in row.get("trade_pnls", ())
        )
        gate = gate_walk_forward_robustness(
            wf, trade_pnls=oos_trade_pnls,
            min_closed_trades=min_closed_trades, confidence=confidence, seed=seed,
        )
        per_candidate.append({"name": name, **gate})
        tests.append({"rows": wf, "trade_pnls": oos_trade_pnls})
    family = family_wise_robustness(tests, alpha=1.0 - confidence)
    # Family-level adequate-sample gate: a multi-symbol scan must not read as
    # "robust" if any member lacks an adequate sample. A lone well-sampled
    # survivor cannot launder a thin one.
    total_closed_trades = sum(int(c.get("total_closed_trades", 0)) for c in per_candidate)
    family_adequate_sample = all(bool(c.get("adequate_sample", False)) for c in per_candidate)
    return {
        "candidates": len(candidates),
        "per_candidate": tuple(per_candidate),
        "family_wise": family,
        "total_closed_trades": total_closed_trades,
        "family_adequate_sample": family_adequate_sample,
        "selection_blocked": True,
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
