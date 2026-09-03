"""Experimental two-sided strategy family for controlled research.

This module is intentionally not part of the production/default baseline yet.
It exists so bearish and bullish regimes can be compared without breaking the
historical baseline. Promotion remains blocked until fee-inclusive walk-forward
evidence supports it.
"""
from __future__ import annotations
from src.features.technical import build_features
from src.strategies.base import CostAssumptions, Candidate, make_candidate


def _candidate(snapshot, costs, name, version, side, move, regime, expiry):
    price = snapshot.mark_price
    entry = snapshot.ask if side == "BUY" else snapshot.bid
    if side == "BUY":
        stop, target = price - max(move * .8, price * .002), price + move
    else:
        stop, target = price + max(move * .8, price * .002), price - move
    c = make_candidate(name=name, version=version, snapshot=snapshot, side=side,
                       entry=entry, stop=stop, target=target,
                       expiry=snapshot.source_ts_ms + expiry, expected_move=move,
                       costs=costs, regime=regime)
    return [c] if c else []


def generate_two_sided_trend(snapshot, costs: CostAssumptions = CostAssumptions()) -> list[Candidate]:
    momentum = build_features(snapshot)["momentum"].value
    if momentum == 0:
        return []
    return _candidate(snapshot, costs, "two_sided_trend", "trend-v2",
                      "BUY" if momentum > 0 else "SELL", abs(momentum) * .5,
                      "TRENDING", 300_000)


def generate_two_sided_mean_reversion(snapshot, costs: CostAssumptions = CostAssumptions()) -> list[Candidate]:
    f = build_features(snapshot)
    deviation = f["sma"].value - snapshot.mark_price
    if deviation == 0:
        return []
    return _candidate(snapshot, costs, "two_sided_mean_reversion", "mean-reversion-v2",
                      "BUY" if deviation > 0 else "SELL", abs(deviation) * .7,
                      "RANGING", 180_000)


def generate_two_sided_breakout(snapshot, costs: CostAssumptions = CostAssumptions()) -> list[Candidate]:
    f = build_features(snapshot)
    candles = tuple(snapshot.candles or snapshot.candles_by_window.get("1m", ()))
    prior = candles[:-1]
    if not prior:
        return []
    price = snapshot.mark_price
    high = max(c.high for c in prior)
    low = min(c.low for c in prior)
    if price < high * .995 and price > low * 1.005:
        return []
    side = "BUY" if price >= high * .995 else "SELL"
    move = max(price * .004, f["volatility"].value * price * 2)
    return _candidate(snapshot, costs, "two_sided_breakout", "breakout-v2",
                      side, move, "HIGH_VOLATILITY", 120_000)


EXPERIMENTAL_STRATEGIES = (
    ("two_sided_trend", generate_two_sided_trend),
    ("two_sided_mean_reversion", generate_two_sided_mean_reversion),
    ("two_sided_breakout", generate_two_sided_breakout),
)
