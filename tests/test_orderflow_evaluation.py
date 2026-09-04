"""Purged chronological evaluation of the order-flow impulse candidate.

Uses the order-flow proxy features (close_location_value, volume_pressure,
market_impact_proxy, spread_proxy) and holding-period labels to evaluate
the strategy through run_baseline, run_walk_forward, and cost stress.
"""
from src.evaluation.baseline import (
    BaselineConfig, run_baseline, run_walk_forward,
)
from src.evaluation.stress import run_combined_stress
from src.features.technical import make_holding_period_labels
from src.market.models import Candle, MarketSnapshot
from src.strategies.orderflow_impulse import generate_orderflow_impulse


def _make_candle(i, base_price, volume, ts_offset):
    variation = (i % 7) - 3
    o = base_price + variation * 0.1
    h = o + 0.5 + (i % 3) * 0.1
    l = o - 0.5 - (i % 3) * 0.1
    c = base_price + variation * 0.05
    return Candle("1m", o, h, l, c, volume, ts_offset + i * 60_000)


def _make_snapshots(n=60, base_price=100.0, volume=10.0):
    snapshots = []
    for i in range(n):
        ts_base = 1_700_000_000_000 + i * 60_000
        candle_offset = ts_base - 19 * 60_000
        candles = [_make_candle(j, base_price + (i % 5) * 0.5, volume, candle_offset)
                   for j in range(20)]
        last = candles[-1]
        spread = 0.02
        price = last.close
        snap = MarketSnapshot(
            "BTCUSDT", price, price - spread, price + spread,
            0.0005, 100, ts_base, ts_base, candles=candles,
        )
        snapshots.append(snap.with_hash())
    return tuple(snapshots)


def test_holding_period_labels_produce_forward_returns():
    closes = [100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0, 103.5, 104.0, 104.5]
    labels = make_holding_period_labels(closes, period=5)
    assert len(labels) == len(closes) - 5
    for label in labels:
        assert "forward_return" in label
        assert "entry_ts_ms" in label
        assert "exit_ts_ms" in label
        assert label["symbol"] == "BTCUSDT"
        assert label["exit_ts_ms"] > label["entry_ts_ms"]


def test_orderflow_strategy_runs_through_baseline():
    snapshots = _make_snapshots(n=50)
    strategies = [("orderflow_impulse", generate_orderflow_impulse)]
    result = run_baseline(snapshots, BaselineConfig(real_funding=False), strategies=strategies)
    assert result.closed_trades >= 0
    assert result.orders >= 0
    assert result.promotion_allowed is False


def test_orderflow_strategy_runs_through_walk_forward():
    snapshots = _make_snapshots(n=120)
    strategies = [("orderflow_impulse", generate_orderflow_impulse)]
    config = BaselineConfig(train_fraction=0.5, test_window=10, embargo=1, real_funding=False)
    rows = run_walk_forward(snapshots, config, strategies=strategies)
    assert len(rows) > 0
    for row in rows:
        assert "closed_trades" in row
        assert "net_pnl" in row
        assert "fees" in row
        assert "slippage" in row
        assert "funding" in row


def test_orderflow_strategy_cost_stress_is_fail_closed():
    snapshots = _make_snapshots(n=60)
    config = BaselineConfig(real_funding=False)
    baseline = run_baseline(snapshots, config, strategies=[("orderflow_impulse", generate_orderflow_impulse)])
    stressed = run_combined_stress(snapshots, config, fee_mult=1.5, funding_mult=2.0, slippage_mult=1.5)
    assert stressed["closed_trades"] <= baseline.closed_trades
    assert stressed["promotion_allowed"] is False


def test_orderflow_strategy_net_pnl_is_not_claimed_as_positive():
    snapshots = _make_snapshots(n=120)
    strategies = [("orderflow_impulse", generate_orderflow_impulse)]
    config = BaselineConfig(train_fraction=0.5, test_window=10, embargo=1, real_funding=False)
    rows = run_walk_forward(snapshots, config, strategies=strategies)
    total_net = sum(row["net_pnl"] for row in rows)
    assert total_net <= 0 or any(row["closed_trades"] == 0 for row in rows)
