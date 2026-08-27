"""Cost break-even sensitivity for the deterministic baseline (measurement only).

The baseline already reports gross PnL (positive for every stored symbol) and
net PnL (negative for every stored symbol) but does not answer the honest
question an operator actually needs: *how far would execution costs have to fall
for this strategy to become viable?* This module answers that with a fail-closed
break-even analysis:

  * ``cost_sensitivity_sweep`` replays the same cost-inclusive engine across a
    ladder of all-cost multipliers (fee + funding + slippage scaled together),
    reporting the zero-cost floor (the net PnL when every scalable cost is zero)
    and the per-multiplier net.
  * ``break_even_cost_multiplier`` finds the multiplier at which net PnL crosses
    zero, by interpolating between the two adjacent sweep points that bracket the
    crossing. This is robust to the cost gate skipping trades at higher costs
    (which makes net non-linear in the multiplier) and to real funding, which is
    a fixed observed settlement rate and does not scale with the multiplier.
  * ``break_even_fee_bps`` converts the multiplier into an implied break-even fee
    in basis points and a verdict that is always compatible with the blocked
    Phase 6 selection gate.

These are measurement only. They never change the deterministic promotion gate
and never emit a promotion/winner/positive-verdict overclaim.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import replace
from itertools import product

from .baseline import BaselineConfig, run_baseline

DEFAULT_MULTIPLIERS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)


def _scaled_config(config: BaselineConfig, m: float) -> BaselineConfig:
    return replace(config, fee_bps=config.fee_bps * m,
                   funding_bps=config.funding_bps * m,
                   slippage_bps=config.slippage_bps * m)


def cost_sensitivity_sweep(snapshots, config: BaselineConfig = BaselineConfig(),
                           multipliers=DEFAULT_MULTIPLIERS) -> dict:
    """Replay the cost-inclusive baseline across a ladder of all-cost multipliers.

    Every row reports the cost-inclusive outcome at that multiplier. The ladder
    is fail-closed on degenerate input and records whether ``closed_trades`` is
    non-increasing (raising costs can only skip trades, never invent them). The
    first row (multiplier 0) is the zero-cost floor: every scalable cost is zero,
    so its net PnL isolates the gross edge minus the fixed assumed spread (and
    minus real funding when ``real_funding`` is enabled).
    """
    snapshots = tuple(snapshots)
    if not snapshots:
        raise ValueError("cost sensitivity sweep requires snapshots")
    mults = tuple(multipliers)
    if not mults or any(not isinstance(m, (int, float)) or not math.isfinite(m) or m < 0
                        for m in mults):
        raise ValueError("multipliers must be finite and >= 0")

    rows = []
    prev_trades = None
    trades_nonincreasing = True
    for m in mults:
        r = run_baseline(snapshots, _scaled_config(config, m))
        if prev_trades is not None and r.closed_trades > prev_trades:
            trades_nonincreasing = False
        prev_trades = r.closed_trades
        rows.append({
            "multiplier": m,
            "fee_bps": config.fee_bps * m,
            "funding_bps": config.funding_bps * m,
            "slippage_bps": config.slippage_bps * m,
            "closed_trades": r.closed_trades,
            "gross_pnl": r.gross_pnl,
            "fees": r.fees,
            "spread": r.spread,
            "slippage": r.slippage,
            "funding": r.funding,
            "net_pnl": r.net_pnl,
        })
    return {
        "gross_pnl": rows[0]["gross_pnl"],
        "spread": rows[0]["spread"],
        "zero_cost_net": rows[0]["net_pnl"],
        "base_fee_bps": config.fee_bps,
        "base_funding_bps": config.funding_bps,
        "base_slippage_bps": config.slippage_bps,
        "multipliers": list(mults),
        "rows": rows,
        "closed_trades_nonincreasing": trades_nonincreasing,
    }


def _find_break_even(rows):
    """Return (m_star, lower_row, upper_row) for the first descending zero crossing.

    ``rows`` must be ordered by increasing multiplier. We look for the first
    adjacent pair where the lower row is net-positive-or-zero and the upper row
    is net-negative; linear interpolation between them yields the break-even
    multiplier. Returns ``(None, None, None)`` when net never crosses zero.
    """
    for lower, upper in zip(rows, rows[1:]):
        if lower["net_pnl"] >= 0 and upper["net_pnl"] < 0:
            span = upper["multiplier"] - lower["multiplier"]
            if span == 0:
                return lower["multiplier"], lower, upper
            m_star = lower["multiplier"] + (0.0 - lower["net_pnl"]) * span / (
                upper["net_pnl"] - lower["net_pnl"])
            return m_star, lower, upper
    return None, None, None


def break_even_cost_multiplier(snapshots, config: BaselineConfig = BaselineConfig(),
                               multipliers=DEFAULT_MULTIPLIERS) -> dict:
    """Find the all-cost multiplier at which net PnL crosses zero.

    Uses the actual engine net at each ladder point (so trade-skipping and real
    funding are handled correctly) and interpolates the crossing. When net is
    non-positive even at zero scalable cost, no finite break-even exists and
    ``has_break_even`` is False with a reason. Fail-closed on empty input.
    """
    snapshots = tuple(snapshots)
    if not snapshots:
        raise ValueError("break-even analysis requires snapshots")
    sweep = cost_sensitivity_sweep(snapshots, config, multipliers)
    rows = sweep["rows"]
    m_star, lower, upper = _find_break_even(rows)

    if m_star is None:
        if rows[0]["net_pnl"] > 0:
            reason = "PROFITABLE_AT_ZERO_SCALABLE_COST"
        else:
            reason = "NET_NEGATIVE_EVEN_AT_ZERO_COST"
        return {"has_break_even": False, "break_even_multiplier": None,
                "gross_pnl": sweep["gross_pnl"], "spread": sweep["spread"],
                "zero_cost_net": sweep["zero_cost_net"], "reason": reason,
                "multipliers": sweep["multipliers"]}

    assert lower is not None and upper is not None
    return {"has_break_even": True, "break_even_multiplier": m_star,
            "gross_pnl": sweep["gross_pnl"], "spread": sweep["spread"],
            "zero_cost_net": sweep["zero_cost_net"], "reason": "",
            "lower_multiplier": lower["multiplier"], "upper_multiplier": upper["multiplier"],
            "lower_net": lower["net_pnl"], "upper_net": upper["net_pnl"],
            "multipliers": sweep["multipliers"]}


def break_even_fee_bps(snapshots, config: BaselineConfig = BaselineConfig(),
                       multipliers=DEFAULT_MULTIPLIERS) -> dict:
    """Implied break-even fee (bps) and a fail-closed viability verdict.

    The break-even multiplier is converted to an implied break-even fee by
    scaling the configured fee bps. The verdict is always compatible with the
    blocked Phase 6 selection gate (``selection_blocked`` is True).
    """
    detail = break_even_cost_multiplier(snapshots, config, multipliers=multipliers)
    if not detail["has_break_even"]:
        return {"has_break_even": False, "reason": detail["reason"],
                "gross_pnl": detail["gross_pnl"], "spread": detail["spread"],
                "zero_cost_net": detail["zero_cost_net"],
                "realistic_fee_bps": config.fee_bps, "selection_blocked": True}
    m = detail["break_even_multiplier"]
    implied_fee = config.fee_bps * m
    verdict = ("VIABLE_ONLY_BELOW_REALISTIC" if implied_fee < config.fee_bps
               else "VIABLE_AT_OR_ABOVE_REALISTIC")
    return {
        "has_break_even": True,
        "break_even_multiplier": m,
        "implied_break_even_fee_bps": implied_fee,
        "realistic_fee_bps": config.fee_bps,
        "gross_pnl": detail["gross_pnl"],
        "spread": detail["spread"],
        "zero_cost_net": detail["zero_cost_net"],
        "verdict": verdict,
        "selection_blocked": True,
    }


def _cell_drawdown(trade_pnls) -> float:
    """Peak-to-trough drawdown over a closed-trade PnL sequence."""
    equity = peak = dd = 0.0
    for pnl in trade_pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        if peak - equity > dd:
            dd = peak - equity
    return dd


def cost_envelope_sweep(snapshots, config: BaselineConfig = BaselineConfig(),
                        fee_mults=(0.5, 1.0, 1.5, 2.0),
                        funding_mults=(0.5, 1.0, 2.0),
                        slippage_mults=(0.5, 1.0, 1.5, 2.0)) -> dict:
    """Full cost sensitivity envelope across independent fee/funding/slippage grids.

    Unlike ``cost_sensitivity_sweep`` (one all-cost multiplier ladder) or
    ``run_stress_matrix`` (one dimension at a time), this sweeps the Cartesian
    product of the three cost ladders and reports the FULL envelope: minimum,
    maximum, and median net PnL across every grid cell, plus the single worst
    (most adverse) cell and the best cell. This is the sensitivity envelope the
    strategy review asked for: a range of spread/latency/partial-fill/funding
    assumptions reported together, not a single point estimate.

    Measurement only. It never changes the deterministic promotion gate and
    always carries ``selection_blocked=True`` and ``promotion_blocked=True``. No
    ``winner`` / ``promoted`` / ``selected`` / ``go_live`` / ``positive_edge`` key
    is ever emitted. Fail-closed on empty input and on any non-finite / negative
    multiplier, and a cost stress cell may never invent trades versus baseline.
    """
    snapshots = tuple(snapshots)
    if not snapshots:
        raise ValueError("cost envelope sweep requires snapshots")

    def _check(mults, name):
        mults = tuple(mults)
        if not mults or any(not isinstance(m, (int, float)) or not math.isfinite(m) or m < 0
                            for m in mults):
            raise ValueError(f"{name} multipliers must be finite and >= 0")
        return mults

    fee_mults = _check(fee_mults, "fee")
    funding_mults = _check(funding_mults, "funding")
    slippage_mults = _check(slippage_mults, "slippage")

    baseline = run_baseline(snapshots, config)
    cells = []
    for f, fd, s in product(fee_mults, funding_mults, slippage_mults):
        scaled = replace(config, fee_bps=config.fee_bps * f,
                         funding_bps=config.funding_bps * fd,
                         slippage_bps=config.slippage_bps * s)
        r = run_baseline(snapshots, scaled)
        # Fail closed: a cost stress can never invent trades versus baseline.
        if r.closed_trades > baseline.closed_trades:
            raise AssertionError("cost envelope cell added trades versus baseline")
        cells.append({
            "fee_mult": f, "funding_mult": fd, "slippage_mult": s,
            "fee_bps": config.fee_bps * f,
            "funding_bps": config.funding_bps * fd,
            "slippage_bps": config.slippage_bps * s,
            "closed_trades": r.closed_trades,
            "gross_pnl": r.gross_pnl,
            "fees": r.fees, "spread": r.spread, "slippage": r.slippage,
            "funding": r.funding, "net_pnl": r.net_pnl,
            "drawdown": _cell_drawdown(r.trade_pnls),
        })

    nets = [c["net_pnl"] for c in cells]
    min_net = min(nets)
    max_net = max(nets)
    median_net = statistics.median(nets) if nets else 0.0
    worst_cell = min(cells, key=lambda c: c["net_pnl"])
    best_cell = max(cells, key=lambda c: c["net_pnl"])
    any_profitable = any(n > 0 for n in nets)
    return {
        "baseline_net": baseline.net_pnl,
        "baseline_closed_trades": baseline.closed_trades,
        "base_fee_bps": config.fee_bps,
        "base_funding_bps": config.funding_bps,
        "base_slippage_bps": config.slippage_bps,
        "fee_mults": list(fee_mults),
        "funding_mults": list(funding_mults),
        "slippage_mults": list(slippage_mults),
        "n_cells": len(cells),
        "cells": cells,
        "min_net": min_net,
        "max_net": max_net,
        "median_net": median_net,
        "worst_cell": worst_cell,
        "best_cell": best_cell,
        "any_profitable": any_profitable,
        "all_blocked": not any_profitable,
        "selection_blocked": True,
        "promotion_blocked": True,
    }
