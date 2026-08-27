"""Strengthen walk-forward evaluation against false-edge (honest-edge guards).

Two gaps this module closes, both MEASUREMENT ONLY (never changes the
deterministic promotion gate and never emits a promoted/selected/winner flag):

1. Per-window multiple testing. The walk-forward pipeline reports aggregate net
   PnL and a window-level bootstrap CI, but never asks how many INDIVIDUAL
   walk-forward windows survive a multiple-testing correction. A strategy that
   aggregates to a positive point estimate only because ONE lucky window landed
   well is not robust edge. We bootstrap each window's trade PnLs with a
   one-sided test (mean <= 0) and apply a Holm step-down correction across
   windows.

2. Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2012). A high Sharpe is easy
   to manufacture under multiple testing and non-Normal trade returns. The DSR
   discounts the observed Sharpe by the number of trials and by the trade
   distribution's skew/kurtosis, answering P(observed SR > false-discovery SR).

Every entry point keeps ``selection_blocked`` True so the result is compatible
with the always-blocked Phase 6 deterministic promotion gate.
"""
from __future__ import annotations

import math
import random
from statistics import mean


def _sr_star(trials: int) -> float:
    """Expected maximum Sharpe among ``trials`` independent tests.

    Approximation of the expected maximum of ``trials`` i.i.d. standard Normal
    draws, used as the false-discovery Sharpe (SR*) in the DSR. ``trials <= 1``
    means no multiple-testing inflation, so SR* = 0.
    """
    trials = max(1, int(trials))
    if trials <= 1:
        return 0.0
    return math.sqrt((1.0 / math.pi) * math.log(trials))


def window_one_sided_p(trades, *, seed: int = 0, samples: int = 2000) -> float:
    """One-sided bootstrap p-value that a window's mean trade PnL <= 0.

    ``p`` is the fraction of bootstrap resamples whose mean is <= 0. A small
    ``p`` rejects the null that the window's edge is non-positive. Deterministic
    for a fixed ``seed``.
    """
    trades = [float(t) for t in trades]
    if not trades:
        raise ValueError("window_one_sided_p requires at least one trade")
    rng = random.Random(seed)
    n = len(trades)
    below = 0
    for _ in range(samples):
        if mean(rng.choices(trades, k=n)) <= 0:
            below += 1
    return below / samples


def holm_stepdown(p_values, *, alpha: float = 0.05):
    """Holm step-down correction across simultaneous one-sided tests.

    Returns ``(rejected_mask, surviving_count)`` where ``rejected_mask[i]`` is
    True when the i-th input p-value survives correction (is rejected as
    non-positive edge). Step-down stops at the first non-rejection, so a single
    lucky small p-value among many large ones cannot drag others along.
    """
    ps = [float(p) for p in p_values]
    m = len(ps)
    if m == 0:
        return [], 0
    if not (0 < alpha < 1):
        raise ValueError("alpha must be in (0, 1)")
    order = sorted(range(m), key=lambda i: ps[i])
    rejected = [False] * m
    count = 0
    for rank, idx in enumerate(order, start=1):
        if ps[idx] <= alpha / (m - rank + 1):
            rejected[idx] = True
            count += 1
        else:
            break
    return rejected, count


def deflated_sharpe(trades, *, trials: int = 1, seed: int = 0, confidence: float = 0.95) -> dict:
    """Deflated Sharpe Ratio for a trade-PnL sample.

    DSR = Phi[ ((SR - SR*) * sqrt(T)) / sqrt(1 - g3*SR + (g4 - 1)/4 * SR^2) ]

    where SR is the sample Sharpe (mean/std), T the number of trades, g3 the
    skewness, g4 the (raw) kurtosis, and SR* the expected false-discovery Sharpe
    for ``trials`` independent tests. ``dsr_prob`` is P(observed SR > SR*);
    ``dsr_positive`` is True when that probability exceeds ``confidence``.

    Fail-closed: fewer than 2 trades, a degenerate zero-variance negative stream,
    or a non-positive denominator all force ``dsr_prob = 0.0`` / ``dsr_positive =
    False``. A zero-variance POSITIVE stream (no uncertainty) yields ``dsr_prob =
    1.0``.
    """
    trades = [float(t) for t in trades]
    n = len(trades)
    sr_star = _sr_star(trials)
    base = {
        "observations": n,
        "sharpe": None,
        "expected_false_sharpe": sr_star,
        "skew": None,
        "kurtosis": None,
        "dsr_prob": 0.0,
        "dsr_positive": False,
        "trials": max(1, int(trials)),
    }
    if n < 2:
        return base
    m = mean(trades)
    var = sum((x - m) ** 2 for x in trades) / (n - 1)
    std = math.sqrt(var)
    if std == 0:
        if m > 0:
            base.update({"sharpe": math.inf, "dsr_prob": 1.0, "dsr_positive": True})
        return base
    sr = m / std
    g3 = sum((x - m) ** 3 for x in trades) / (n * std ** 3)
    g4 = sum((x - m) ** 4 for x in trades) / (n * std ** 4)
    denom = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr ** 2
    if denom <= 0:
        dsr_prob = 0.0
    else:
        z = ((sr - sr_star) * math.sqrt(n)) / math.sqrt(denom)
        dsr_prob = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    base.update({
        "sharpe": sr,
        "skew": g3,
        "kurtosis": g4,
        "dsr_prob": dsr_prob,
        "dsr_positive": dsr_prob > confidence,
    })
    return base


def strengthen_walk_forward(rows, *, min_closed_trades: int = 30, confidence: float = 0.95,
                            seed: int = 0, trials: int | None = None) -> dict:
    """Combine per-window Holm correction and DSR into honest-edge facts.

    Measurement only. ``robust_edge`` is a descriptive verdict that requires
    BOTH the deflated-Sharpe check AND that edge survives in at least half the
    walk-forward windows after Holm correction (not one lucky window). It never
    feeds the deterministic promotion gate, which stays ``NEGATIVE_NET_PNL`` and
    ``selection_blocked`` True.
    """
    rows = tuple(rows)
    if not rows:
        raise ValueError("strengthen_walk_forward requires at least one window row")
    if not isinstance(min_closed_trades, int) or min_closed_trades < 1:
        raise ValueError("min_closed_trades must be a positive integer")
    if not isinstance(confidence, (int, float)) or not (0 < confidence < 1):
        raise ValueError("confidence must be a finite number strictly between 0 and 1")
    alpha = 1.0 - confidence

    total_closed = sum(int(r.get("closed_trades", 0)) for r in rows)
    adequate_sample = total_closed >= min_closed_trades

    window_ps: list[float] = []
    pooled: list[float] = []
    windows_with_trades = 0
    for r in rows:
        tp = r.get("trade_pnls") or []
        if tp:
            windows_with_trades += 1
            pooled.extend(float(t) for t in tp)
            window_ps.append(window_one_sided_p(tp, seed=seed))

    holm_rejected, holm_surviving = (
        holm_stepdown(window_ps, alpha=alpha) if window_ps else ([], 0)
    )
    n_trials = trials if trials is not None else max(1, windows_with_trades)
    dsr = deflated_sharpe(pooled, trials=n_trials, seed=seed, confidence=confidence)

    # Edge must show in at least half the windows (after Holm) AND pass the DSR
    # variability check. This is the honest bar that a lone lucky window fails.
    robust_threshold = max(1, windows_with_trades // 2)
    robust_edge = bool(
        adequate_sample and dsr["dsr_positive"] and holm_surviving >= robust_threshold
    )

    return {
        "windows": len(rows),
        "windows_with_trades": windows_with_trades,
        "holm_total": len(window_ps),
        "holm_surviving": holm_surviving,
        "holm_rejected": holm_rejected,
        "adequate_sample": adequate_sample,
        "total_closed_trades": total_closed,
        "min_closed_trades": min_closed_trades,
        "dsr_prob": dsr["dsr_prob"],
        "dsr_positive": dsr["dsr_positive"],
        "expected_false_sharpe": dsr["expected_false_sharpe"],
        "sharpe": dsr["sharpe"],
        "skew": dsr["skew"],
        "kurtosis": dsr["kurtosis"],
        "trials": dsr["trials"],
        "robust_edge": robust_edge,
        "selection_blocked": True,
    }
