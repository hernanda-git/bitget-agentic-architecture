"""Pre-registered order-flow impulse candidate.

Uses candle-geometry order-flow proxies (close_location_value, volume_pressure,
market_impact_proxy, spread_proxy) and a fixed holding period to generate a
directional impulse candidate. This is an isolated research family; it is not
part of the canonical baseline until independent evaluation supports it.

Parameters are fixed before any result is inspected; no optimizer or
test-set selection is permitted.
"""
from __future__ import annotations
from src.features.technical import build_features
from src.strategies.base import CostAssumptions, Candidate, make_candidate

HOLDING_PERIOD_BARS = 5
EXPIRY_MS = HOLDING_PERIOD_BARS * 60_000

MIN_CLV_DEVIATION = 0.15
MIN_VOLUME_PRESSURE = 0.05
MAX_SPREAD_BPS = 5.0
ATR_TARGET_MULTIPLE = 1.5
ATR_STOP_MULTIPLE = 1.0
MIN_RETURN = 0.001


def generate_orderflow_impulse(
    snapshot, costs: CostAssumptions = CostAssumptions()
) -> list[Candidate]:
    f = build_features(snapshot)
    clv = f["close_location_value"].value
    volume_pressure = f["volume_pressure"].value
    market_impact = f["market_impact_proxy"].value
    spread_bps = f["spread_proxy"].value
    atr = f["atr"].value

    if atr <= 0:
        return []

    # Directional pressure: CLV deviation from midpoint (0.5).
    clv_signal = clv - 0.5
    if abs(clv_signal) < MIN_CLV_DEVIATION:
        return []

    # Volume pressure must confirm CLV direction.
    if abs(volume_pressure) < MIN_VOLUME_PRESSURE or (volume_pressure > 0) != (clv_signal > 0):
        return []

    # Market impact (body direction) must confirm the order-flow signal.
    if (market_impact > 0) != (clv_signal > 0):  # Market impact must confirm CLV direction
        return []

    # Spread filter: reject when observed spread is too wide.
    if spread_bps > MAX_SPREAD_BPS:
        return []

    side = "BUY" if clv_signal > 0 else "SELL"
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
        name="orderflow_impulse", version="orderflow-v1",
        snapshot=snapshot, side=side, entry=entry, stop=stop, target=target,
        expiry=snapshot.source_ts_ms + EXPIRY_MS, expected_move=move,
        costs=costs, regime="ORDERFLOW_IMPULSE",
    )
    return [candidate] if candidate else []
