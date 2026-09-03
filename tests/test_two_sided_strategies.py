"""Phase 55 RED: strategies must express both market directions.

This is a structural correction, not a profitability claim. A directional
research family that only emits BUY candidates cannot be evaluated fairly across
bull and bear regimes. Tests require side-specific stop/target geometry and keep
cost gates intact.
"""
from src.market.models import Candle, MarketSnapshot
from src.strategies.base import CostAssumptions
from src.strategies.two_sided import (
    generate_two_sided_trend,
    generate_two_sided_mean_reversion,
    generate_two_sided_breakout,
)


def snapshot(closes, *, spread=0.02):
    ts = 1_700_000_000_000
    candles = tuple(Candle("1m", min(c, closes[i-1] if i else c) - .1,
                           max(c, closes[i-1] if i else c) + .1,
                           min(c, closes[i-1] if i else c) - .2,
                           c, 100 + i * 10, ts + i * 60_000)
                     for i, c in enumerate(closes))
    mark = closes[-1]
    return MarketSnapshot("BTCUSDT", mark, mark - spread / 2, mark + spread / 2,
                          0.0001, 100, candles[-1].source_ts_ms,
                          candles[-1].source_ts_ms, candles=candles).with_hash()


def test_trend_continuation_emits_sell_for_negative_momentum():
    candidate = generate_two_sided_trend(snapshot([110, 108, 106, 104, 100]), CostAssumptions())[0]
    assert candidate.side == "SELL"
    assert candidate.stop_loss > candidate.entry > candidate.take_profit


def test_mean_reversion_emits_sell_when_price_is_above_sma():
    candidate = generate_two_sided_mean_reversion(snapshot([100, 100, 100, 100, 110]), CostAssumptions())[0]
    assert candidate.side == "SELL"
    assert candidate.stop_loss > candidate.entry > candidate.take_profit


def test_volatility_breakout_emits_sell_at_downside_range_break():
    candidate = generate_two_sided_breakout(snapshot([110, 109, 108, 107, 95]), CostAssumptions())[0]
    assert candidate.side == "SELL"
    assert candidate.stop_loss > candidate.entry > candidate.take_profit
