"""Fail-closed per-window data-quality gate for walk-forward evaluation (TDD: RED first).

The global ``data_quality_report`` used by ``evaluate_real_history.py`` can pass
while a HOLE sits inside one walk-forward TEST window. A walk-forward window is
the slice we actually trade on, so an internal gap silently distorts the few
trades inside it and can launder a spurious edge. This module slices every
train/test window from the original dataset, re-runs the established structural
+ coverage checks on each slice, and fails closed when ANY slice is unsound.

Unblocked work: strengthens walk-forward evaluation + data-quality checks. Pure
measurement, never touches the deterministic promotion gate or selection.
"""
from pathlib import Path

import pytest

from src.market.models import Candle
from src.market.history import (
    HistoryDataset,
    FundingRecord,
    snapshots_from_dataset,
)
from src.evaluation.baseline import BaselineConfig, run_walk_forward

from src.evaluation.walk_forward_quality import (
    WalkForwardQualityResult,
    gate_walk_forward_dataset,
    slice_dataset,
    window_plan_from_dataset,
    evaluate_window_quality,
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
        fetched_at_ms = max(c.source_ts_ms for c in candles)
    return HistoryDataset(
        symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="1m",
        fetched_at_ms=fetched_at_ms, candles=tuple(candles),
        funding=tuple(FundingRecord(ft, rate) for ft, rate in funding),
        assumed_half_spread_bps=0.5,
    )


def test_slice_dataset_returns_subdataset_within_range():
    candles = _mk_contiguous(n=30)
    ds = _mk_dataset(candles)
    sub = slice_dataset(ds, candles[5].source_ts_ms, candles[14].source_ts_ms)
    assert len(sub.candles) == 10
    assert sub.candles[0].source_ts_ms == candles[5].source_ts_ms
    assert sub.candles[-1].source_ts_ms == candles[14].source_ts_ms


def test_window_plan_matches_run_walk_forward_indices():
    """The gate's plan must line up exactly with the engine's walk-forward split."""
    candles = _mk_contiguous(n=60)
    ds = _mk_dataset(candles)
    snapshots = snapshots_from_dataset(ds)
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=10)
    wf_rows = run_walk_forward(snapshots, config)
    plan = window_plan_from_dataset(
        ds, train_fraction=config.train_fraction, embargo=config.embargo,
        test_window=config.test_window,
    )
    assert len(plan) == len(wf_rows)
    for p, row in zip(plan, wf_rows):
        assert p["test_start_idx"] == row["test_start"]
        assert p["test_end_idx"] == row["test_end"]
        # Timestamps of the plan map back to the same snapshots.
        assert snapshots[p["test_start_idx"]].source_ts_ms == p["test_start_ms"]
        assert snapshots[p["test_end_idx"]].source_ts_ms == p["test_end_ms"]


def test_clean_dataset_passes_window_quality_gate():
    candles = _mk_contiguous(n=60)
    ds = _mk_dataset(candles)
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=10)
    result = gate_walk_forward_dataset(ds, config)
    assert isinstance(result, WalkForwardQualityResult)
    assert result.all_ok is True
    assert result.failed_windows == 0
    assert result.reject_reason == ""


def test_gap_inside_test_window_fails_closed():
    """A hole inside a window we trade on must reject, never pass silently."""
    candles = _mk_contiguous(n=60)
    # Drop one candle that sits inside the first test window (indices 37..46).
    dropped = candles[40]
    candles = [c for c in candles if c.source_ts_ms != dropped.source_ts_ms]
    ds = _mk_dataset(candles)
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=10)
    result = gate_walk_forward_dataset(ds, config)
    assert result.all_ok is False
    assert result.failed_windows >= 1
    assert "window" in result.reject_reason.lower()


def test_bad_price_inside_test_window_fails_closed():
    candles = _mk_contiguous(n=60)
    bad = list(candles)
    # Corrupt a candle inside the first test window with a non-finite high.
    idx = 41
    corrupted = Candle("1m", bad[idx].open, float("inf"), bad[idx].low,
                       bad[idx].close, bad[idx].volume, bad[idx].source_ts_ms)
    bad[idx] = corrupted
    ds = _mk_dataset(bad)
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=10)
    result = gate_walk_forward_dataset(ds, config)
    assert result.all_ok is False
    assert result.failed_windows >= 1


def test_gate_rejects_before_evaluation_cli_on_window_gap(tmp_path):
    """The real entrypoint must refuse a windowed gap before any heavy replay."""
    import json
    import subprocess
    import sys

    candles = _mk_contiguous(n=60)
    dropped = candles[40]
    candles = [c for c in candles if c.source_ts_ms != dropped.source_ts_ms]
    ds = _mk_dataset(candles)
    dataset_path = tmp_path / "holey.json"
    dataset_path.write_text(json.dumps(ds.to_dict(), indent=2, sort_keys=True) + "\n")
    output_path = tmp_path / "out.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_real_history.py"),
         "--dataset", str(dataset_path), "--output", str(output_path),
         "--no-resource-budget"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 4
    assert "WALK_FORWARD_QUALITY_REJECTED" in (proc.stdout + proc.stderr)
    # Fail closed: no report written when quality is rejected.
    assert not output_path.exists()
