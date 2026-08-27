"""Fail-closed per-window data-quality gate for walk-forward evaluation.

The global ``data_quality_report`` used by ``evaluate_real_history.py`` can pass
while a HOLE sits inside one walk-forward TEST window. A walk-forward window is
the slice the engine actually trades on, so an internal gap silently distorts
the few trades inside it and can launder a spurious edge.

This module slices every train/test window from the original dataset, re-runs
the established structural + coverage checks on each slice, and fails closed
when ANY slice is unsound. It is pure measurement: it never mutates the dataset,
never touches the deterministic promotion gate, and never emits a
promotion/selection/winner flag.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.market.history import (
    HistoryDataset,
    DataQualityReport,
    coverage_gate,
    data_quality_report,
)


@dataclass(frozen=True)
class WindowQualityResult:
    """Per-window quality findings for one train/test split."""

    window_index: int
    train_ok: bool
    test_ok: bool
    expected_train_bars: int
    actual_train_bars: int
    expected_test_bars: int
    actual_test_bars: int
    train_report: dict
    test_report: dict


@dataclass(frozen=True)
class WalkForwardQualityResult:
    """Aggregated fail-closed verdict over all walk-forward windows."""

    all_ok: bool
    windows: tuple[WindowQualityResult, ...]
    failed_windows: int
    reject_reason: str

    def as_dict(self) -> dict:
        return {
            "all_ok": self.all_ok,
            "windows": len(self.windows),
            "failed_windows": self.failed_windows,
            "reject_reason": self.reject_reason,
            "window_results": [w.__dict__ for w in self.windows],
        }


def slice_dataset(dataset: HistoryDataset, start_ms: int, end_ms: int) -> HistoryDataset:
    """Return a sub-dataset whose candles fall within ``[start_ms, end_ms]`` (inclusive)."""
    if start_ms > end_ms:
        raise ValueError("slice_dataset requires start_ms <= end_ms")
    candles = tuple(c for c in dataset.candles if start_ms <= c.source_ts_ms <= end_ms)
    if not candles:
        raise ValueError("slice_dataset produced no candles for the given range")
    funding = tuple(f for f in dataset.funding if start_ms <= f.funding_time_ms <= end_ms)
    return HistoryDataset(
        symbol=dataset.symbol, product_type=dataset.product_type,
        granularity=dataset.granularity, fetched_at_ms=dataset.fetched_at_ms,
        candles=candles, funding=funding,
        assumed_half_spread_bps=dataset.assumed_half_spread_bps, source=dataset.source,
    )


def window_plan_from_dataset(dataset: HistoryDataset, *, train_fraction: float = 0.6,
                             embargo: int = 1, test_window: int = 10) -> tuple[dict, ...]:
    """Replicate ``run_walk_forward``'s index split using candle timestamps.

    The engine splits the snapshot sequence (one snapshot per candle, in order)
    with ``cut = max(1, int(n * train_fraction))`` and then walks non-overlapping
    test windows of size ``test_window`` separated by ``embargo`` bars. This
    reproduces the exact same train/test index ranges and exposes their
    timestamps so the quality gate can slice the original candle series.
    """
    candles = dataset.candles
    n = len(candles)
    if not (0 < train_fraction < 1):
        raise ValueError("train_fraction must be in (0, 1)")
    if embargo < 0 or test_window < 1:
        raise ValueError("embargo must be >= 0 and test_window >= 1")
    if n < 1:
        raise ValueError("window plan requires at least one candle")
    cut = max(1, int(n * train_fraction))
    ts = [c.source_ts_ms for c in candles]
    window = test_window
    windows: list[dict] = []
    test_start_idx = cut + embargo
    while test_start_idx + window <= n:
        test_end_idx = test_start_idx + window - 1
        train_end_idx = test_start_idx - embargo - 1
        train_end_idx = max(train_end_idx, 0)
        windows.append({
            "window_index": len(windows),
            "train_start_idx": 0, "train_end_idx": train_end_idx,
            "test_start_idx": test_start_idx, "test_end_idx": test_end_idx,
            "train_start_ms": ts[0], "train_end_ms": ts[train_end_idx],
            "test_start_ms": ts[test_start_idx], "test_end_ms": ts[test_end_idx],
        })
        test_start_idx = test_end_idx + 1 + embargo
    if not windows:
        raise ValueError("walk-forward plan requires at least one complete test window")
    return tuple(windows)


def evaluate_window_quality(dataset: HistoryDataset, windows: Iterable[dict], *,
                            max_missing_fraction: float = 0.25) -> WalkForwardQualityResult:
    """Fail closed if ANY train/test window slice is structurally unsound or gapped.

    Test windows must be gap-free (exact bar count) because they are the slices
    the engine trades on. Training windows may tolerate sparse coverage up to
    ``max_missing_fraction`` but must still be structurally sound.
    """
    windows = tuple(windows)
    results: list[WindowQualityResult] = []
    failed = 0
    reasons: list[str] = []
    for w in windows:
        train_ds = slice_dataset(dataset, w["train_start_ms"], w["train_end_ms"])
        test_ds = slice_dataset(dataset, w["test_start_ms"], w["test_end_ms"])
        train_report = data_quality_report(train_ds)
        test_report = data_quality_report(test_ds)

        expected_train = w["train_end_idx"] - w["train_start_idx"] + 1
        expected_test = w["test_end_idx"] - w["test_start_idx"] + 1
        actual_train = len(train_ds.candles)
        actual_test = len(test_ds.candles)

        # Training slice: structurally sound + coverage within tolerance.
        train_ok = (
            train_report.ok
            and coverage_gate(train_report, max_missing_fraction=max_missing_fraction)
        )
        # Test slice: structurally sound, exactly the expected bars, AND no
        # internal gap. A hole between two present bars keeps the bar count
        # correct but still distorts the few trades inside the window, so the
        # gap check is mandatory (catches holes the bar-count check cannot).
        test_ok = (
            test_report.ok
            and actual_test == expected_test
            and len(test_report.gaps) == 0
        )

        results.append(WindowQualityResult(
            window_index=w["window_index"], train_ok=train_ok, test_ok=test_ok,
            expected_train_bars=expected_train, actual_train_bars=actual_train,
            expected_test_bars=expected_test, actual_test_bars=actual_test,
            train_report=train_report.as_dict(), test_report=test_report.as_dict(),
        ))
        if not (train_ok and test_ok):
            failed += 1
            reasons.append(
                f"window {w['window_index']}: train_ok={train_ok} test_ok={test_ok} "
                f"train_bars={actual_train}/{expected_train} test_bars={actual_test}/{expected_test}"
            )
    return WalkForwardQualityResult(
        all_ok=failed == 0, windows=tuple(results), failed_windows=failed,
        reject_reason="; ".join(reasons),
    )


def gate_walk_forward_dataset(dataset: HistoryDataset, config, *,
                              max_missing_fraction: float = 0.25) -> WalkForwardQualityResult:
    """Build the walk-forward plan from ``config`` and evaluate window quality.

    ``config`` must expose ``train_fraction``, ``embargo``, and ``test_window``
    (the same fields consumed by ``run_walk_forward``). The result is fail-closed:
    ``all_ok`` is False when any train/test slice is unsound or gapped.
    """
    plan = window_plan_from_dataset(
        dataset, train_fraction=config.train_fraction, embargo=config.embargo,
        test_window=config.test_window,
    )
    return evaluate_window_quality(dataset, plan, max_missing_fraction=max_missing_fraction)
