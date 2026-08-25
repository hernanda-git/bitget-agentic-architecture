from __future__ import annotations
from enum import Enum
from src.features.technical import build_features

class Regime(str, Enum):
    TRENDING="TRENDING"; RANGING="RANGING"; HIGH_VOLATILITY="HIGH_VOLATILITY"; LOW_VOLATILITY="LOW_VOLATILITY"; LIQUIDATION_EVENT="LIQUIDATION_EVENT"; DATA_DEGRADED="DATA_DEGRADED"

def classify_regime(snapshot, minimum_candles: int = 5) -> Regime:
    candles = snapshot.candles or snapshot.candles_by_window.get("1m", ())
    if len(candles) < minimum_candles: return Regime.DATA_DEGRADED
    f = build_features(snapshot); closes = [c.close for c in candles]
    for i in range(1, len(closes) - 1):
        drop = closes[i] / closes[i - 1] - 1
        recovery = closes[i + 1] / closes[i] - 1
        if drop <= -.20 and 0 <= recovery <= .05: return Regime.LIQUIDATION_EVENT
    if f["volatility"].value >= .08: return Regime.HIGH_VOLATILITY
    if abs(f["momentum"].value) >= max(closes[-1] * .015, f["volatility"].value * closes[-1] * 2): return Regime.TRENDING
    if f["volatility"].value <= .001: return Regime.LOW_VOLATILITY
    return Regime.RANGING
