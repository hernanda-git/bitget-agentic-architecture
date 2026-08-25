from __future__ import annotations
from src.features.registry import FeatureValue, feature
from src.market.models import MarketSnapshot

def _closes(snapshot: MarketSnapshot) -> list[float]:
    return [c.close for c in (snapshot.candles or snapshot.candles_by_window.get("1m", ()))]

def build_features(snapshot: MarketSnapshot) -> dict[str, FeatureValue]:
    closes = _closes(snapshot)
    if not closes:
        raise ValueError("features require candles")
    def add(name: str, value: float, parameters: dict) -> FeatureValue:
        return feature(name, value, snapshot.snapshot_hash or snapshot.computed_hash(), snapshot.source_ts_ms, parameters)
    window = min(3, len(closes))
    sma = sum(closes[-window:]) / window
    returns = [(closes[i] / closes[i-1]) - 1 for i in range(1, len(closes))]
    volatility = (sum((x - sum(returns[-window:]) / window) ** 2 for x in returns[-window:]) / window) ** 0.5 if returns else 0.0
    momentum = closes[-1] - closes[max(0, len(closes) - window)]
    high = max(c.high for c in (snapshot.candles or snapshot.candles_by_window.get("1m", ())))
    low = min(c.low for c in (snapshot.candles or snapshot.candles_by_window.get("1m", ())))
    return {"sma": add("sma", sma, {"window": window}), "volatility": add("volatility", volatility, {"window": window}),
            "momentum": add("momentum", momentum, {"window": window}), "range_high": add("range_high", high, {"window": len(closes)}),
            "range_low": add("range_low", low, {"window": len(closes)})}
