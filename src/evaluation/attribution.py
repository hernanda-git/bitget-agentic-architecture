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


def attribute_performance_by_regime(
    strategy_returns: Dict[str, List[float]],
    regime_labels: List[str],
    *,
    min_samples: int = 30,
    confidence: float = 0.95,
    bootstrap_samples: int = 2000,
    seed: int = 0,
) -> dict:
    """Decompose measured per-strategy returns by market regime (descriptive).

    Slices the SAME aligned per-step return stream by an externally supplied
    ``regime_labels`` series (one label per shared timestep, produced by
    ``src.strategies.regime.classify_regime`` in the real pipeline) and reports,
    fail-closed and descriptively:

    * per-regime equal-weight blend expectancy + bootstrap CI + sample size
    * per-strategy / per-regime expectancy matrix
    * edge concentration: which regime carries the most |net| and its share

    This answers the honest-edge question the family-level attribution cannot:
    *is the edge concentrated in one regime?* A strategy whose aggregate is
    positive only because of a single lucky regime is fragile, and a lone
    dominant regime can launder a spurious edge past the cross-sectional
    dispersion check.

    It never emits a winner / promotion / selection flag and ``selection_blocked``
    is always ``True``, so it cannot change the deterministic Phase 6 promotion
    gate (which stays blocked in this repository). No network, no credentials,
    no signed calls, no orders.

    ``regime_labels`` must be aligned (same length) to every strategy series.
    """
    if len(strategy_returns) < 2:
        raise ValueError("need at least 2 strategies for regime attribution")
    n_steps = len(regime_labels)
    if n_steps < 1:
        raise ValueError("regime_labels must be non-empty")

    # Fail-closed input validation: alignment + finiteness.
    cleaned: "Dict[str, List[float]]" = {}
    for name, series in strategy_returns.items():
        if not series:
            raise ValueError("empty return series for strategy %s" % name)
        if len(series) != n_steps:
            raise ValueError(
                "strategy %s series length %d is not aligned to %d regime labels"
                % (name, len(series), n_steps)
            )
        for v in series:
            if not _FINITE(v):
                raise ValueError("non-finite return for strategy %s" % name)
        cleaned[name] = [float(v) for v in series]

    # Gather every strategy's return at each regime's steps (the equal-weight
    # blend is the concatenation; it equals the per-step cross-strategy mean).
    regime_order: List[str] = []
    regime_returns: "Dict[str, List[float]]" = {}
    for i, reg in enumerate(regime_labels):
        if reg not in regime_returns:
            regime_returns[reg] = []
            regime_order.append(reg)
        for name in cleaned:
            regime_returns[reg].append(cleaned[name][i])

    regimes: "Dict[str, dict]" = {}
    total_abs_net = 0.0
    for reg in regime_order:
        rets = regime_returns[reg]
        net = sum(rets)
        expectancy = net / len(rets) if rets else 0.0
        ci = bootstrap_ci(rets, samples=bootstrap_samples, confidence=confidence, seed=seed)
        n_strategies = sum(
            1 for name in cleaned if any(regime_labels[i] == reg for i in range(n_steps))
        )
        regimes[reg] = {
            "n": len(rets),
            "n_strategies": n_strategies,
            "expectancy": expectancy,
            "bootstrap_ci": list(ci),
            "net": net,
            "share_of_abs_net": None,  # filled after total_abs_net known
        }
        total_abs_net += abs(net)

    for reg in regimes:
        regimes[reg]["share_of_abs_net"] = (
            (abs(regimes[reg]["net"]) / total_abs_net) if total_abs_net > 0 else None
        )

    # Per-strategy / per-regime expectancy matrix.
    strategies: "Dict[str, Dict[str, dict]]" = {}
    for name in sorted(cleaned):
        strategies[name] = {}
        for reg in regime_order:
            rs = [cleaned[name][i] for i in range(n_steps) if regime_labels[i] == reg]
            net_s = sum(rs)
            expectancy_s = net_s / len(rs) if rs else 0.0
            ci_s = bootstrap_ci(rs, samples=bootstrap_samples, confidence=confidence, seed=seed)
            strategies[name][reg] = {
                "n": len(rs),
                "expectancy": expectancy_s,
                "bootstrap_ci": list(ci_s),
            }

    # Edge concentration: which regime carries the most |net|, and its share.
    if regimes:
        dominant_name, dominant = max(regimes.items(), key=lambda kv: abs(kv[1]["net"]))
        dominant_regime = dominant_name
        dominant_share = dominant["share_of_abs_net"]
        positive_count = sum(1 for r in regimes.values() if r["expectancy"] > 0)
    else:
        dominant_regime = None
        dominant_share = None
        positive_count = 0

    return {
        "selection_blocked": True,
        "attribution_is_descriptive": True,
        "n_strategies": len(cleaned),
        "n_steps": n_steps,
        "regimes": regimes,
        "strategies": strategies,
        "edge_concentration": {
            "dominant_regime": dominant_regime,
            "dominant_share_abs": dominant_share,
            "regimes_with_positive_expectancy": positive_count,
        },
        "regime_labels_observed": sorted(regimes.keys()),
    }
