"""Purged chronological walk-forward evaluation for funding-basis (H-003).

Extends the purged holding-period label infrastructure from Phase 62
(evaluate_purged_holding_periods) and the walk-forward boundary from
Phase 63 (evaluate_purged_orderflow_walk_forward) to the funding-basis
mean-reversion hypothesis (H-003, derivatives_microstructure). When
evaluating the funding-basis strategy across walk-forward windows,
holding-period labels must respect the purged constraint *per window*:
every exit_idx must stay strictly within its own test window, so no
future information leaks across the train/test boundary.

This is measurement only — it never changes the deterministic promotion
gate (which stays NEGATIVE_NET_PNL / blocked).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.evaluation.holding_period import evaluate_purged_holding_periods

# Default walk-forward configuration
DEFAULT_TEST_WINDOW = 10
DEFAULT_EMBARGO = 1


@dataclass(frozen=True)
class PurgedFundingBasisWindowResult:
    """Result for one purged walk-forward window."""
    window_index: int
    test_start: int
    test_end: int
    labels: list[dict]
    label_count: int
    purge_violations: int

    @property
    def purge_ok(self) -> bool:
        return self.purge_violations == 0


class _WalkForwardConfig:
    """Minimal config-like object for _walk_forward_windows."""
    def __init__(self, train_fraction: float, test_window: int, embargo: int):
        self.train_fraction = train_fraction
        self.test_window = test_window
        self.embargo = embargo


def _walk_forward_windows(n: int, config: _WalkForwardConfig) -> list[dict]:
    """Compute walk-forward window boundaries (mirrors run_walk_forward)."""
    cut = max(1, int(n * config.train_fraction))
    window = config.test_window
    embargo = config.embargo
    windows = []
    test_start = cut + embargo
    while test_start + window <= n:
        test_end = test_start + window - 1
        windows.append({
            "train_start": 0,
            "train_end": test_start - embargo - 1,
            "test_start": test_start,
            "test_end": test_end,
        })
        test_start = test_end + 1 + embargo
    return windows


def evaluate_purged_funding_basis_walk_forward(
    closes: list[float],
    period: int,
    *,
    test_window: int = DEFAULT_TEST_WINDOW,
    embargo: int = DEFAULT_EMBARGO,
    train_fraction: float = 0.6,
    symbol: str = "BTCUSDT",
    start_ts_ms: int = 0,
) -> list[dict]:
    """Create purged holding-period labels across walk-forward test windows
    for the funding-basis mean-reversion hypothesis (H-003).

    For each walk-forward test window, produces forward-return labels
    where every exit_idx is strictly bounded by the window's test_end,
    preventing lookahead across the train/test boundary. The purged
    constraint is enforced by construction: labels are generated only
    for bars where ``i + period <= test_end``.

    Args:
        closes: Ordered list of closing prices.
        period: Number of bars to hold (lookahead). Must be positive.
        test_window: Number of bars per walk-forward test window.
        embargo: Number of embargoed bars between train and test.
        train_fraction: Fraction of data used for training.
        symbol: Symbol identifier for label provenance.
        start_ts_ms: Starting timestamp in milliseconds.

    Returns:
        List of label dicts, each carrying:
        - forward_return: the return from entry to exit
        - entry_idx: the index of the entry bar
        - exit_idx: the index of the exit bar (strictly within the test window)
        - entry_ts_ms: the entry timestamp
        - exit_ts_ms: the exit timestamp
        - symbol: the symbol identifier
        - window_index: which walk-forward window this label belongs to
        - test_start / test_end: the window boundaries

    Raises:
        ValueError: if period is not positive, or if test_window < 1.
    """
    if period <= 0:
        raise ValueError("holding period must be positive")
    if test_window < 1:
        raise ValueError("test_window must be positive")

    n = len(closes)
    if n <= 1:
        return []

    config = _WalkForwardConfig(train_fraction, test_window, embargo)
    windows = _walk_forward_windows(n, config)

    all_labels = []
    for win_idx, win in enumerate(windows):
        test_start = win["test_start"]
        test_end = win["test_end"]
        # Purged: labels only where i + period <= test_end and i >= test_start
        for i in range(test_start, min(test_end - period + 1, n - period)):
            if i + period >= n:
                break
            all_labels.append({
                "forward_return": closes[i + period] / closes[i] - 1,
                "entry_idx": i,
                "exit_idx": i + period,
                "entry_ts_ms": start_ts_ms + i * 60_000,
                "exit_ts_ms": start_ts_ms + (i + period) * 60_000,
                "symbol": symbol,
                "window_index": win_idx,
                "test_start": test_start,
                "test_end": test_end,
            })

    return all_labels
