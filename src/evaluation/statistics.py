"""Small-sample-aware descriptive statistics for offline trade evaluation."""
from __future__ import annotations
import math, random
from collections import Counter
from statistics import mean, median


def _drawdown(values):
    equity = peak = 0.0; max_dd = 0.0; recovery = None; trough = 0
    for i, value in enumerate(values):
        equity += value
        if equity > peak:
            peak = equity
            if max_dd and recovery is None: recovery = i - trough
        dd = peak - equity
        if dd > max_dd: max_dd, trough, recovery = dd, i, None
    return max_dd, recovery


def bootstrap_ci(values, *, samples=2000, confidence=0.95, seed=0):
    values = tuple(float(v) for v in values)
    if not values or samples < 1: return (None, None)
    rng = random.Random(seed); n = len(values)
    estimates = sorted(mean(rng.choices(values, k=n)) for _ in range(samples))
    lo = (1-confidence)/2; hi = 1-lo
    return (estimates[int(lo*(samples-1))], estimates[int(hi*(samples-1))])


def compute_statistics(trades, *, min_samples=30, bootstrap_samples=2000, seed=0,
                       parameter_groups=None, symbol_groups=None, regime_groups=None):
    values = tuple(float(v) for v in trades)
    if len(values) < min_samples:
        return {"status":"NOT_EVIDENCED", "reason":"MINIMUM_SAMPLE_NOT_MET", "samples":len(values), "minimum_samples":min_samples}
    wins = [v for v in values if v > 0]; losses = [v for v in values if v < 0]
    dd, recovery = _drawdown(values)
    gross_profit = sum(wins); gross_loss = -sum(losses)
    loss_runs=[]; run=0
    for v in values:
        run = run + 1 if v < 0 else 0
        loss_runs.append(run)
    out = {
        "status":"EVIDENCED", "samples":len(values), "minimum_samples":min_samples,
        "expectancy":mean(values), "r_expectancy": mean(values) / (mean([abs(v) for v in losses]) if losses else 1.0),
        "expectancy_r": mean(values) / (mean([abs(v) for v in losses]) if losses else 1.0),
        "bootstrap_ci": bootstrap_ci(values, samples=bootstrap_samples, seed=seed),
        "profit_factor": gross_profit / gross_loss if gross_loss else math.inf,
        "drawdown": dd, "recovery": recovery,
        "win_loss": {"wins":len(wins), "losses":len(losses), "win_rate":len(wins)/len(values), "average_win":mean(wins) if wins else 0.0, "average_loss":mean(losses) if losses else 0.0},
        "tail": {"p05": sorted(values)[max(0, int(.05*(len(values)-1)))], "median":median(values), "p95":sorted(values)[int(.95*(len(values)-1))]},
        "consecutive_losses": max(loss_runs, default=0),
        "concentration": {"top_trade_share": max((abs(v) for v in values), default=0.0) / sum(abs(v) for v in values) if any(values) else 0.0},
    }
    for name, groups in (("parameter_stability", parameter_groups), ("symbol_stability", symbol_groups), ("regime_stability", regime_groups)):
        out[name] = {str(k): compute_statistics(v, min_samples=min_samples, bootstrap_samples=100, seed=seed)["status"] for k,v in (groups or {}).items()}
    return out


# Named entry-point aliases keep the module convenient for callers that use
# either the noun or verb form, without introducing a second implementation.
summarize_trades = compute_statistics
statistics_report = compute_statistics
