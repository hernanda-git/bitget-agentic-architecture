"""Pre-registered volume-confirmed directional impulse candidate.

This is an isolated research family. It is not part of the canonical baseline
until independent evaluation supports it. Parameters are fixed here before any
result is inspected; no optimizer or test-set selection is permitted.
"""
from __future__ import annotations
from src.features.technical import build_features
from src.strategies.base import CostAssumptions, Candidate, make_candidate

LOOKBACK_RETURN = 3
MIN_RETURN = 0.005
MIN_VOLUME_ZSCORE = 1.5
ATR_TARGET_MULTIPLE = 1.5
ATR_STOP_MULTIPLE = 1.0
EXPIRY_MS = 5 * 60_000


def generate_volume_confirmed_impulse(
    snapshot, costs: CostAssumptions = CostAssumptions()
) -> list[Candidate]:
    f = build_features(snapshot)
    impulse = f["return_3"].value
    volume_zscore = f["volume_zscore"].value
    atr = f["atr"].value
    if abs(impulse) < MIN_RETURN or volume_zscore < MIN_VOLUME_ZSCORE or atr <= 0:
        return []
    side = "BUY" if impulse > 0 else "SELL"
    move = atr * ATR_TARGET_MULTIPLE
    price = snapshot.mark_price
    entry = snapshot.ask if side == "BUY" else snapshot.bid
    if side == "BUY":
        stop = price - atr * ATR_STOP_MULTIPLE
        target = price + move
    else:
        stop = price + atr * ATR_STOP_MULTIPLE
        target = price - move
    candidate = make_candidate(
        name="volume_confirmed_impulse", version="volume-impulse-v1",
        snapshot=snapshot, side=side, entry=entry, stop=stop, target=target,
        expiry=snapshot.source_ts_ms + EXPIRY_MS, expected_move=move,
        costs=costs, regime="IMPULSE",
    )
    return [candidate] if candidate else []
