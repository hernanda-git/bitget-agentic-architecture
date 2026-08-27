"""Honest strategy attribution for already-measured per-strategy return series.

Given a set of candidate strategy return series (e.g. walk-forward
out-of-sample return streams), this module decomposes the aggregate result into
per-family contributions and reports dispersion. It is strictly DESCRIPTIVE.

* It never emits a winner / promotion / selection flag.
* ``selection_blocked`` is always ``True`` so it cannot change the deterministic
  Phase 6 promotion gate (which stays ``NEGATIVE_NET_PNL`` / blocked).
* No network, no credentials, no signed calls, no orders.

Reuses the small-sample bootstrap CI from ``src.evaluation.statistics`` so the
uncertainty reported here matches the rest of the evaluation stack.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from typing import Dict, List

from src.evaluation.statistics import bootstrap_ci

_FINITE = math.isfinite


def attribute_performance(
    strategy_returns: Dict[str, List[float]],
    *,
    min_samples: int = 30,
    confidence: float = 0.95,
    bootstrap_samples: int = 2000,
    seed: int = 0,
) -> dict:
    """Decompose measured per-strategy returns into an honest attribution report.

    Parameters
    ----------
    strategy_returns:
        Mapping of strategy family name to its per-step return series. Must
        contain at least two families; each series must be non-empty and finite.
    min_samples:
        Minimum number of observations for a family to be marked ``EVIDENCED``.
    confidence, bootstrap_samples, seed:
        Passed through to the bootstrap CI used for per-strategy and blend
        expectancy intervals.

    Returns
    -------
    dict
        An attribution report. Always carries ``selection_blocked=True`` and
        ``attribution_is_descriptive=True``. Never contains a winner / promotion
        / selection verdict.

    Raises
    ------
    ValueError
        Fail-closed on fewer than two families, an empty series, or a non-finite
        value.
    """
    if len(strategy_returns) < 2:
        raise ValueError("need at least 2 strategies for attribution")

    # Fail-closed input validation.
    for name, series in strategy_returns.items():
        if not series:
            raise ValueError("empty return series for strategy %s" % name)
        for v in series:
            if not _FINITE(v):
                raise ValueError("non-finite return for strategy %s" % name)

    def _sharpe(values, mean_val):
        n = len(values)
        if n < 2:
            return None
        var = sum((v - mean_val) ** 2 for v in values) / (n - 1)
        std = math.sqrt(var)
        if std == 0:
            return None
        return mean_val / std

    strategies: "OrderedDict[str, dict]" = OrderedDict()
    total_net = 0.0
    total_abs = 0.0
    for name in sorted(strategy_returns.keys()):
        series = [float(v) for v in strategy_returns[name]]
        n = len(series)
        net_total = sum(series)
        abs_total = sum(abs(v) for v in series)
        expectancy = net_total / n if n else 0.0
        ci = bootstrap_ci(series, samples=bootstrap_samples, confidence=confidence, seed=seed)
        evidenced = n >= min_samples
        strategies[name] = {
            "n": n,
            "expectancy": expectancy,
            "bootstrap_ci": ci,
            "sharpe": _sharpe(series, expectancy),
            "net_total": net_total,
            "abs_total": abs_total,
            "share_of_net": None,  # filled after total_net known
            "evidence_status": "EVIDENCED" if evidenced else "NOT_EVIDENCED",
        }
        total_net += net_total
        total_abs += abs_total

    # Per-strategy share of net contribution (None when net cancels to zero).
    for s in strategies.values():
        s["share_of_net"] = (s["net_total"] / total_net) if total_net != 0 else None

    # Descriptive equal-weight blend across families, aligned to the shortest
    # series. Clearly labelled: it is NOT a recommended allocation and NOT a
    # selection signal.
    min_len = min(s["n"] for s in strategies.values())
    blend_returns: List[float] = []
    if min_len > 0:
        for i in range(min_len):
            blend_returns.append(
                sum(strategy_returns[name][i] for name in strategies) / len(strategies)
            )
    blend_expectancy = (sum(blend_returns) / len(blend_returns)) if blend_returns else 0.0
    blend_ci = bootstrap_ci(
        blend_returns, samples=bootstrap_samples, confidence=confidence, seed=seed
    )

    # Cross-sectional dispersion: how concentrated is the edge?
    top_abs_name = max(strategies.items(), key=lambda kv: kv[1]["abs_total"])[0]
    top_abs_share = (
        (strategies[top_abs_name]["abs_total"] / total_abs) if total_abs > 0 else 0.0
    )
    net_positive = sum(1 for s in strategies.values() if s["net_total"] > 0)
    net_negative = sum(1 for s in strategies.values() if s["net_total"] < 0)
    dominant_net_name = max(strategies.items(), key=lambda kv: abs(kv[1]["net_total"]))[0]

    evidenced_count = sum(1 for s in strategies.values() if s["evidence_status"] == "EVIDENCED")

    return {
        "selection_blocked": True,
        "attribution_is_descriptive": True,
        "n_strategies": len(strategies),
        "evidenced_count": evidenced_count,
        "strategies": strategies,
        "total_net": total_net,
        "total_abs": total_abs,
        "blend": {
            "is_descriptive": True,
            "selection_blocked": True,
            "n": min_len,
            "expectancy": blend_expectancy,
            "bootstrap_ci": blend_ci,
        },
        "cross_sectional": {
            "top_abs_contributor": top_abs_name,
            "top_abs_share": top_abs_share,
            "net_positive_count": net_positive,
            "net_negative_count": net_negative,
            "dominant_net_contributor": dominant_net_name,
        },
    }
