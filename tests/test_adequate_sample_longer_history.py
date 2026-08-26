"""RED: the stored public-history datasets must satisfy the adequate-sample
robustness gate (>=30 closed trades) so expectancy can be measured with a
confidence interval at statistical power.

The previous phase-9 gate reported ``adequate_sample=False`` everywhere because
the stored datasets were only 240 candles per symbol/granularity, yielding
8-16 closed trades (below the 30-trade threshold). This test documents the
requirement and fails until longer public history is acquired.

No signed calls, no credentials, no orders. Pure offline evaluation of
already-stored (or freshly acquired) unauthenticated public history.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from src.market.history import load_dataset, snapshots_from_dataset
from src.evaluation.baseline import (
    BaselineConfig,
    gate_walk_forward_robustness,
    run_baseline,
    run_walk_forward,
)

ROOT = Path(__file__).resolve().parents[1]
MIN_CLOSED_TRADES = 30
# Target candle count that the acquisition step must deliver. 240 candles gave
# 8-16 closed trades; a 5-6x larger window is required to clear the gate.
MIN_CANDLES = 1000
DATASETS = ["BTCUSDT_1m", "BTCUSDT_5m", "ETHUSDT_1m", "ETHUSDT_5m"]


@pytest.mark.parametrize("name", DATASETS)
def test_stored_dataset_has_enough_candles(name):
    """RED: stored history must carry enough candles to attempt the gate."""
    path = ROOT / "data" / "history" / f"{name}.json"
    if not path.exists():
        pytest.skip(f"dataset {name} not yet acquired")
    ds = load_dataset(path)
    assert len(ds.candles) >= MIN_CANDLES, (
        f"{name}: {len(ds.candles)} candles, need >= {MIN_CANDLES} to clear the "
        f"adequate-sample gate (240 candles only yielded 8-16 closed trades)"
    )


@pytest.mark.parametrize("name", DATASETS)
def test_real_history_satisfies_adequate_sample(name):
    """RED: the evaluation must clear the adequate-sample robustness gate."""
    path = ROOT / "data" / "history" / f"{name}.json"
    if not path.exists():
        pytest.skip(f"dataset {name} not yet acquired")
    ds = load_dataset(path)
    snapshots = snapshots_from_dataset(ds)
    config = BaselineConfig(real_funding=True)

    baseline = run_baseline(snapshots, config)
    walk_forward = run_walk_forward(snapshots, config)
    robustness = gate_walk_forward_robustness(
        walk_forward, trade_pnls=baseline.trade_pnls, min_closed_trades=MIN_CLOSED_TRADES
    )

    assert robustness["windows_with_trades"] >= 1, (
        f"{name}: walk-forward produced no executable windows"
    )
    assert robustness["adequate_sample"] is True, (
        f"{name}: only {robustness['total_closed_trades']} closed trades, need "
        f">= {MIN_CLOSED_TRADES} to satisfy the adequate-sample robustness gate"
    )
