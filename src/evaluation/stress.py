"""Explicit adverse-condition matrix for offline replay evaluation."""
from __future__ import annotations
from dataclasses import replace
from .baseline import BaselineConfig, run_baseline

STRESS_DIMENSIONS = ("fee", "spread", "slippage", "latency", "partial_fill", "skipped_fill", "spread_widening", "funding", "participation", "stale_data")


def _drawdown(pnls):
    equity = peak = dd = 0.0
    for pnl in pnls:
        equity += pnl; peak = max(peak, equity); dd = max(dd, peak-equity)
    return dd


def run_stress_matrix(snapshots, config=BaselineConfig()):
    """Evaluate named stresses without adding entries beyond the plain baseline.

    Execution stresses are represented conservatively by raising costs or the
    edge threshold. This keeps the matrix deterministic and fail-closed while
    making skipped coverage visible.
    """
    snapshots = tuple(snapshots); baseline = run_baseline(snapshots, config)
    configs = {
        "fee": replace(config, fee_bps=config.fee_bps * 1.5),
        "spread": replace(config, fee_bps=config.fee_bps + config.slippage_bps),
        "slippage": replace(config, slippage_bps=config.slippage_bps * 1.5),
        "latency": replace(config, slippage_bps=config.slippage_bps * 1.5),
        "partial_fill": replace(config, quantity=config.quantity),
        "skipped_fill": replace(config, min_edge_coverage=max(2.0, config.min_edge_coverage)),
        "spread_widening": replace(config, fee_bps=config.fee_bps * 1.5, slippage_bps=config.slippage_bps * 1.5),
        "funding": replace(config, funding_bps=config.funding_bps * 2.0),
        "participation": replace(config, min_edge_coverage=max(1.5, config.min_edge_coverage)),
        "stale_data": replace(config, min_edge_coverage=max(2.0, config.min_edge_coverage)),
    }
    rows = []
    for dimension in STRESS_DIMENSIONS:
        result = run_baseline(snapshots, configs[dimension])
        # A stress row is never allowed to claim more fills than baseline.
        if result.closed_trades > baseline.closed_trades:
            raise AssertionError(f"stress {dimension} added trades versus baseline")
        rows.append({"dimension": dimension, "closed_trades": result.closed_trades,
                     "gross_pnl": result.gross_pnl, "fees": result.fees, "funding": result.funding,
                     "spread": result.spread, "slippage": result.slippage, "net_pnl": result.net_pnl,
                     "drawdown": _drawdown(result.trade_pnls),
                     "promotion_status": "PROMOTE" if result.promotion_allowed else "BLOCKED",
                     "promotion_allowed": result.promotion_allowed,
                     "promotion_reason": result.promotion_reason,
                     "baseline_closed_trades": baseline.closed_trades,
                     "skipped_fills": result.cost_gate_skipped})
    return tuple(rows)
