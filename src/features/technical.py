from __future__ import annotations
import math
from statistics import mean, pstdev
from src.features.registry import FeatureValue, feature
from src.market.models import Candle, MarketSnapshot


def _candles(snapshot: MarketSnapshot):
    return tuple(snapshot.candles or snapshot.candles_by_window.get("1m", ()))


def _closes(snapshot: MarketSnapshot) -> list[float]:
    return [c.close for c in _candles(snapshot)]


def build_features(snapshot: MarketSnapshot) -> dict[str, FeatureValue]:
    """Build causal technical and market-context features.

    Existing v1 primitives are retained for compatibility. New v2 features are
    deliberately conservative: they use only candles present in this snapshot,
    preserve snapshot provenance, and represent unavailable optional inputs as
    neutral zero values rather than inventing observations.
    """
    candles = _candles(snapshot)
    closes = [c.close for c in candles]
    if not closes:
        raise ValueError("features require candles")

    def add(name: str, value: float, parameters: dict) -> FeatureValue:
        return feature(name, value, snapshot.snapshot_hash or snapshot.computed_hash(),
                       snapshot.source_ts_ms, parameters)

    def add_v2(name: str, value: float, parameters: dict) -> FeatureValue:
        return feature(name, value, snapshot.snapshot_hash or snapshot.computed_hash(),
                       snapshot.source_ts_ms, parameters, version="technical-v2")

    window = min(3, len(closes))
    sma = sum(closes[-window:]) / window
    returns = [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes))]
    recent_returns = returns[-window:]
    avg_return = sum(recent_returns) / window if recent_returns else 0.0
    volatility = (sum((x - avg_return) ** 2 for x in recent_returns) / window) ** 0.5 if returns else 0.0
    momentum = closes[-1] - closes[max(0, len(closes) - window)]
    high = max(c.high for c in candles)
    low = min(c.low for c in candles)

    result = {
        "sma": add("sma", sma, {"window": window}),
        "volatility": add("volatility", volatility, {"window": window}),
        "momentum": add("momentum", momentum, {"window": window}),
        "range_high": add("range_high", high, {"window": len(closes)}),
        "range_low": add("range_low", low, {"window": len(closes)}),
    }

    # Causal returns: return_3 falls back to the oldest available close when
    # fewer than four candles exist; no future candle can enter the calculation.
    return_1 = closes[-1] / closes[-2] - 1 if len(closes) >= 2 else 0.0
    base_3 = closes[-4] if len(closes) >= 4 else closes[0]
    return_3 = closes[-1] / base_3 - 1 if base_3 else 0.0

    true_ranges = []
    for i, candle in enumerate(candles):
        previous_close = candles[i - 1].close if i else candle.open
        true_ranges.append(max(candle.high - candle.low,
                               abs(candle.high - previous_close),
                               abs(candle.low - previous_close)))
    atr_window = min(14, len(true_ranges))
    atr = mean(true_ranges[-atr_window:]) if true_ranges else 0.0

    volumes = [c.volume for c in candles]
    volume_window = volumes[-min(20, len(volumes)):]
    volume_mean = mean(volume_window) if volume_window else 0.0
    volume_std = pstdev(volume_window) if len(volume_window) > 1 else 0.0
    volume_zscore = ((volumes[-1] - volume_mean) / volume_std
                     if volume_std > 0 and math.isfinite(volume_std) else 0.0)

    # A single snapshot has no historical OI series. Returning zero for change
    # is explicit "unavailable", not an inferred trend.
    result.update({
        "return_1": add_v2("return_1", return_1, {"lookback": 1}),
        "return_3": add_v2("return_3", return_3, {"lookback": 3}),
        "atr": add_v2("atr", atr, {"window": atr_window}),
        "volume_zscore": add_v2("volume_zscore", volume_zscore, {"window": len(volume_window)}),
        "funding_rate": add_v2("funding_rate", float(snapshot.funding_rate or 0.0), {"source": "snapshot"}),
        "open_interest": add_v2("open_interest", float(snapshot.open_interest or 0.0), {"source": "snapshot"}),
        "open_interest_change": add_v2("open_interest_change", 0.0, {"source": "unavailable_without_history"}),
    })

    # ---- Order-flow / depth proxy features (v2) ----
    # Close-location value: where the close sits within the bar range.
    # 1.0 = close at high (bullish intrabar pressure), 0.0 = close at low, 0.5 = midpoint.
    last = candles[-1]
    rng = last.high - last.low
    clv = (last.close - last.low) / rng if rng > 0 else 0.5

    # Volume pressure: directional pressure combining CLV deviation from midpoint
    # with volume anomaly. Sign tracks CLV - 0.5 so bullish position => positive.
    vol_mult = 1.0 + (volume_zscore if math.isfinite(volume_zscore) else 0.0)
    volume_pressure = (clv - 0.5) * vol_mult

    # Market impact proxy: body-to-range ratio. Positive = bullish body
    # (close above open), negative = bearish body.
    body = last.close - last.open
    market_impact_proxy = body / rng if rng > 0 else 0.0

    # Spread proxy: observed top-of-book spread in bps from the snapshot.
    spread_proxy = float(snapshot.spread_bps)

    result.update({
        "close_location_value": add_v2("close_location_value", clv, {"source": "candle_geometry"}),
        "volume_pressure": add_v2("volume_pressure", volume_pressure, {"source": "candle_geometry_volume"}),
        "market_impact_proxy": add_v2("market_impact_proxy", market_impact_proxy, {"source": "candle_geometry"}),
        "spread_proxy": add_v2("spread_proxy", spread_proxy, {"source": "observed_spread"}),
    })

    return result


def make_holding_period_labels(closes: list[float], period: int,
                                symbol: str = "BTCUSDT",
                                start_ts_ms: int = 0) -> list[dict]:
    """Create forward-return labels over a configurable holding period.

    Each label is the return from bar ``i`` to bar ``i + period``:
    ``closes[i + period] / closes[i] - 1``. Labels whose exit index
    exceeds the available history are dropped so no future information
    leaks into the current-step feature set.
    """
    if period <= 0:
        raise ValueError("holding period must be positive")
    if len(closes) <= period:
        return []
    labels = []
    for i in range(len(closes) - period):
        labels.append({
            "forward_return": closes[i + period] / closes[i] - 1,
            "entry_ts_ms": start_ts_ms + i * 60_000,
            "exit_ts_ms": start_ts_ms + (i + period) * 60_000,
            "symbol": symbol,
        })
    return labels
