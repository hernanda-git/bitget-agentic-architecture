"""Phase 62 — Purged holding-period evaluation (RED phase).

Tests evaluate_purged_holding_periods which produces forward-return
labels for configurable holding periods with purged chronological
validation. This function does not yet exist — the test must fail
with ImportError until the implementation is written.
"""
import pytest


def test_evaluate_purged_holding_periods_module_exists():
    """The evaluate_purged_holding_periods function must exist."""
    from src.evaluation.holding_period import evaluate_purged_holding_periods
    assert callable(evaluate_purged_holding_periods)


def test_evaluate_purged_holding_periods_returns_labels():
    """Function returns labels with forward_return, entry_ts_ms, exit_ts_ms."""
    from src.evaluation.holding_period import evaluate_purged_holding_periods
    closes = [100.0, 101.0, 102.0, 103.0, 105.0, 107.0]
    labels = evaluate_purged_holding_periods(closes, period=2)
    assert len(labels) == len(closes) - 2
    for label in labels:
        assert "forward_return" in label
        assert "entry_ts_ms" in label
        assert "exit_ts_ms" in label
        assert label["forward_return"] == closes[label["exit_idx"]] / closes[label["entry_idx"]] - 1


def test_evaluate_purged_holding_periods_raises_on_invalid_period():
    """Invalid period must raise ValueError."""
    from src.evaluation.holding_period import evaluate_purged_holding_periods
    with pytest.raises(ValueError):
        evaluate_purged_holding_periods([100.0, 101.0], period=0)


def test_evaluate_purged_holding_periods_empty_on_insufficient_data():
    """Not enough bars for the holding period => no labels."""
    from src.evaluation.holding_period import evaluate_purged_holding_periods
    labels = evaluate_purged_holding_periods([100.0, 101.0], period=3)
    assert labels == []


def test_evaluate_purged_holding_periods_no_future_leak():
    """Labels must not reference bars beyond the available history.

    This is the purged constraint: exit index must be within bounds.
    """
    from src.evaluation.holding_period import evaluate_purged_holding_periods
    closes = [100.0, 100.5, 101.0, 101.5, 102.0]
    labels = evaluate_purged_holding_periods(closes, period=3)
    for label in labels:
        assert label["exit_idx"] < len(closes), "exit index must be within bounds"
        assert label["entry_idx"] < len(closes), "entry index must be within bounds"
        assert label["exit_idx"] > label["entry_idx"], "exit must be after entry"