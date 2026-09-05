"""Funding-basis mean reversion strategy (H-003).

Funding-extreme mean reversion before settlement.
When funding rate is extremely positive, longs are paying heavily —
signal SELL (mean reversion against the crowded long side). When
extremely negative, shorts are paying — signal BUY. Neutral funding
produces no signal. Wide spread blocks entry because execution costs
exceed any theoretical edge.

This is measurement-only research. No profitability claim is made.
"""
from __future__ import annotations

from src.features.technical import build_features
from src.strategies.base import CostAssumptions, Candidate, make_candidate

MIN_FUNDING_RATE = 0.0005
MAX_SPREAD_BPS = 10.0
ATR_TARGET_MULTIPLE = 2.0
ATR_STOP_MULTIPLE = 1.5
EXPIRY_MS = 5 * 60_000


def generate_funding_basis(
    snapshot, costs: CostAssumptions = CostAssumptions()
) -> list[Candidate]:
    funding_rate = snapshot.funding_rate or 0.0

    if snapshot.spread_bps > MAX_SPREAD_BPS:
        return []

    if abs(funding_rate) < MIN_FUNDING_RATE:
        return []

    side = "SELL" if funding_rate > 0 else "BUY"

    f = build_features(snapshot)
    atr = f["atr"].value
    price = snapshot.mark_price
    move = atr * ATR_TARGET_MULTIPLE

    if atr <= 0 or move <= 0:
        return []

    entry = snapshot.ask if side == "BUY" else snapshot.bid

    if side == "BUY":
        stop = price - atr * ATR_STOP_MULTIPLE
        target = price + move
    else:
        stop = price + atr * ATR_STOP_MULTIPLE
        target = price - move

    candidate = make_candidate(
        name="funding_basis", version="funding-basis-v1",
        snapshot=snapshot, side=side, entry=entry, stop=stop, target=target,
        expiry=snapshot.source_ts_ms + EXPIRY_MS, expected_move=move,
        costs=costs, regime="FUNDING_BASIS",
    )
    return [candidate] if candidate else []
