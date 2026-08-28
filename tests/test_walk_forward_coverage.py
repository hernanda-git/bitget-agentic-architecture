"""Fail-closed walk-forward coverage pre-check (TDD: RED first).

A walk-forward with too few / too-short test windows cannot support a
statistically meaningful out-of-sample verdict, yet the engine will happily
trade a handful of bars and laud the aggregate. This module reports, fail
closed, how many complete test windows the dataset supports at the configured
``test_window`` and whether that count is statistically adequate, plus the
largest test-window length that still yields an adequate window count.

The function is measurement-only: it never flips the deterministic promotion
gate. ``evaluate_real_history.py`` may opt into a hard fail-closed gate via
``--require-wf-coverage``; by default the verdict is reported in the payload so
existing 2500-bar corpus runs are not broken.

Unblocked work: strengthens walk-forward evaluation + data-quality checks.
No signed calls, no orders, no promotion/selection/winner flag.
"""
from pathlib import Path

import pytest

from src.market.models import Candle
from src.market.history import HistoryDataset, FundingRecord
from src.evaluation.baseline import BaselineConfig

from src.evaluation.walk_forward_coverage import (
    WalkForwardCoverage,
    _count_windows,
    _recommend_test_window,
    plan_walk_forward_coverage,
)

ROOT = Path(__file__).resolve().parents[1]


def _mk_contiguous(symbol="BTCUSDT", n=60, step_ms=60_000, base_ts=1_700_000_000_000,
                   start_close=100.0):
    candles = []
    for i in range(n):
        c = start_close + i * 0.1
        candles.append(Candle("1m", c - 0.5, c + 1.0, c - 1.0, c, 10.0, base_ts + i * step_ms))
    return candles


def _mk_dataset(candles, funding=(), fetched_at_ms=None):
    if fetched_at_ms is None:
        fetched_at_ms = (max(c.source_ts_ms for c in candles) if candles
                         else 1_700_000_000_000)
    return HistoryDataset(
        symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="1m",
        fetched_at_ms=fetched_at_ms, candles=tuple(candles),
        funding=tuple(FundingRecord(ft, rate) for ft, rate in funding),
        assumed_half_spread_bps=0.5,
    )


def test_count_windows_matches_manual_formula():
    # n=2500, cut=1500, embargo=1, window=10 -> non-overlapping windows.
    n, cut, embargo, w = 2500, 1500, 1, 10
    got = _count_windows(n, cut, embargo, w)
    # last start L with L+w<=n -> L<=n-w; L = cut+embargo + k*(w+embargo)
    expected = (n - w - (cut + embargo)) // (w + embargo) + 1
    assert got == expected
    assert got > 50  # many short windows fit in a long series


def test_recommend_test_window_larger_with_more_data():
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=10)
    small = _recommend_test_window(1200, config, min_windows=5)
    large = _recommend_test_window(6000, config, min_windows=5)
    assert large > small >= 1


def test_coverage_short_dataset_inadequate():
    """120 bars at the default 10-bar window yield far fewer than 5 adequate windows."""
    ds = _mk_dataset(_mk_contiguous(n=120))
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=10)
    cov = plan_walk_forward_coverage(ds, config, min_windows=5, min_bars_per_window=50)
    assert isinstance(cov, WalkForwardCoverage)
    assert cov.windows < 5
    assert cov.test_bars_per_window == 10
    assert cov.adequate is False
    assert cov.recommended_test_window >= 1


def test_coverage_adequate_with_long_window_on_long_series():
    ds = _mk_dataset(_mk_contiguous(n=2500))
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=50)
    cov = plan_walk_forward_coverage(ds, config, min_windows=5, min_bars_per_window=50)
    assert cov.windows >= 5
    assert cov.test_bars_per_window == 50
    assert cov.adequate is True
    assert cov.total_test_bars == cov.windows * 50


def test_coverage_rejects_empty_dataset():
    ds = _mk_dataset([])
    config = BaselineConfig()
    with pytest.raises(ValueError):
        plan_walk_forward_coverage(ds, config)


def test_coverage_payload_has_required_keys():
    ds = _mk_dataset(_mk_contiguous(n=2500))
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=50)
    cov = plan_walk_forward_coverage(ds, config, min_windows=5, min_bars_per_window=50)
    d = cov.as_dict()
    for key in ("windows", "train_bars", "test_bars_per_window", "total_test_bars",
                "recommended_test_window", "adequate", "min_windows",
                "min_bars_per_window", "config_test_window"):
        assert key in d
    assert d["config_test_window"] == 50
