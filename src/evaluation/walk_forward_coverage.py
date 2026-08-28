"""Fail-closed walk-forward coverage pre-check.

A walk-forward with too few / too-short test windows cannot support a
statistically meaningful out-of-sample verdict, yet the engine will happily
trade a handful of bars and laud the aggregate. This module reports, fail
closed, how many complete test windows the dataset supports at the configured
``test_window`` and whether that count is statistically adequate, plus the
largest test-window length that still yields an adequate window count.

The function is measurement-only: it never flips the deterministic promotion
gate. ``evaluate_real_history.py`` may opt into a hard fail-closed gate via
``--require-wf-coverage``; by default the verdict is reported in the payload so
existing short-corpus runs are not broken.

Unblocked work: strengthens walk-forward evaluation + data-quality checks.
No signed calls, no orders, no promotion/selection/winner flag.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.market.history import HistoryDataset
from src.evaluation.walk_forward_quality import window_plan_from_dataset


@dataclass(frozen=True)
class WalkForwardCoverage:
    """Fail-closed coverage verdict for one walk-forward configuration."""

    windows: int
    train_bars: int
    test_bars_per_window: int
    total_test_bars: int
    recommended_test_window: int
    adequate: bool
    min_windows: int
    min_bars_per_window: int
    config_test_window: int
    # Fail-closed promotion reporting: coverage adequacy is necessary-but-not
    # sufficient for strategy selection. The deterministic baseline is negative,
    # so selection stays blocked regardless of coverage. This mirrors the
    # always-blocked Phase 6 policy used across the other measurement-only
    # evaluation modules (walk-forward robustness, candidate-family, cost
    # envelope). It reports the gate state; it never flips the promotion verdict.
    selection_blocked: bool = True

    def as_dict(self) -> dict:
        return {
            "windows": self.windows,
            "train_bars": self.train_bars,
            "test_bars_per_window": self.test_bars_per_window,
            "total_test_bars": self.total_test_bars,
            "recommended_test_window": self.recommended_test_window,
            "adequate": self.adequate,
            "min_windows": self.min_windows,
            "min_bars_per_window": self.min_bars_per_window,
            "config_test_window": self.config_test_window,
            "selection_blocked": self.selection_blocked,
        }


def _count_windows(n: int, cut: int, embargo: int, w: int) -> int:
    """Number of complete non-overlapping ``w``-bar test windows in ``[cut+embargo, n)``."""
    if w < 1 or cut < 0 or n <= 0:
        return 0
    count = 0
    test_start = cut + embargo
    while test_start + w <= n:
        count += 1
        test_start += w + embargo
    return count


def _recommend_test_window(n: int, config, *, min_windows: int = 5) -> int:
    """Largest test-window length that still yields >= ``min_windows`` complete windows.

    Returns 0 when the series is too short for even one embargo'd window, and 1
    when no longer window reaches the window-count target (the smallest window
    always maximizes the count). Fail closed: never claims adequacy it cannot
    support.
    """
    cut = max(1, int(n * config.train_fraction))
    available = n - cut - config.embargo
    if available < 1:
        return 0
    for w in range(available, 0, -1):
        if _count_windows(n, cut, config.embargo, w) >= min_windows:
            return w
    return 1


def plan_walk_forward_coverage(dataset: HistoryDataset, config, *,
                               min_windows: int = 5,
                               min_bars_per_window: int = 50) -> WalkForwardCoverage:
    """Fail-closed walk-forward coverage facts for ``dataset`` under ``config``.

    ``adequate`` is True only when BOTH the complete-window count meets
    ``min_windows`` AND each test window carries at least ``min_bars_per_window``
    bars. The recommendation reports the largest window length that still meets
    the window-count target, so a researcher knows what test window the current
    dataset supports before trusting any aggregate verdict.
    """
    if not isinstance(min_windows, int) or min_windows < 1:
        raise ValueError("min_windows must be a positive integer")
    if not isinstance(min_bars_per_window, int) or min_bars_per_window < 1:
        raise ValueError("min_bars_per_window must be a positive integer")

    candles = getattr(dataset, "candles", ())
    n = len(candles)
    if n < 1:
        raise ValueError("walk-forward coverage requires at least one candle")

    try:
        windows = window_plan_from_dataset(
            dataset, train_fraction=config.train_fraction,
            embargo=config.embargo, test_window=config.test_window,
        )
    except ValueError:
        windows = ()

    windows_count = len(windows)
    test_bars_per_window = int(config.test_window)
    train_bars = (
        windows[0]["train_end_idx"] - windows[0]["train_start_idx"] + 1
        if windows else 0
    )
    total_test_bars = windows_count * test_bars_per_window
    recommended = _recommend_test_window(n, config, min_windows=min_windows)
    adequate = (windows_count >= min_windows) and (test_bars_per_window >= min_bars_per_window)
    return WalkForwardCoverage(
        windows=windows_count,
        train_bars=train_bars,
        test_bars_per_window=test_bars_per_window,
        total_test_bars=total_test_bars,
        recommended_test_window=recommended,
        adequate=adequate,
        min_windows=min_windows,
        min_bars_per_window=min_bars_per_window,
        config_test_window=test_bars_per_window,
        selection_blocked=True,
    )


def require_wf_coverage_exit_code(dataset: HistoryDataset, config, *,
                                  min_windows: int = 5,
                                  min_bars_per_window: int = 50) -> int:
    """Fail-closed coverage verdict mapped to a process exit code.

    Returns ``0`` when the dataset supports an adequate walk-forward coverage at
    the configured ``test_window`` (>= ``min_windows`` complete windows, each
    carrying >= ``min_bars_per_window`` bars). Returns ``6`` otherwise, so a
    caller can reject a thin corpus without inventing an out-of-sample verdict.

    Measurement only: it never flips the deterministic promotion gate, never
    places orders, and never emits a selection/winner flag. The deterministic
    baseline stays negative; this function reports adequacy facts, nothing more.
    """
    cov = plan_walk_forward_coverage(
        dataset, config, min_windows=min_windows, min_bars_per_window=min_bars_per_window
    )
    return 0 if cov.adequate else 6

