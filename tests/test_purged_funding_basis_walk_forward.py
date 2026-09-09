"""Phase 64 RED: purged chronological walk-forward evaluation for funding-basis (H-003).

Tests evaluate_purged_funding_basis_walk_forward() which enforces strict purging
when computing holding-period labels across walk-forward test windows for the
funding-basis mean-reversion hypothesis (H-003, derivatives_microstructure).
The purged constraint guarantees every exit_idx stays strictly within the test
window, so no future information leaks across the train/test boundary.
"""
import pytest
from src.evaluation.funding_basis_evaluation import evaluate_purged_funding_basis_walk_forward


def _make_closes(n=60, base=100.0):
    """Generate synthetic closing prices."""
    import random
    random.seed(42)
    closes = [base]
    for _ in range(n - 1):
        closes.append(closes[-1] + random.uniform(-0.5, 0.5))
    return closes


def test_evaluate_purged_funding_basis_module_exists():
    """The evaluate_purged_funding_basis_walk_forward function must exist."""
    assert callable(evaluate_purged_funding_basis_walk_forward)


def test_evaluate_purged_funding_basis_returns_valid_labels():
    """Function returns purged labels for each walk-forward window."""
    closes = _make_closes(n=50)
    labels = evaluate_purged_funding_basis_walk_forward(closes, period=5, test_window=10, embargo=1)
    assert isinstance(labels, list)
    for label in labels:
        assert "forward_return" in label
        assert "entry_idx" in label
        assert "exit_idx" in label
        assert "window_index" in label
        assert label["exit_idx"] < len(closes), "exit index must be within bounds"
        assert label["entry_idx"] < label["exit_idx"], "entry must precede exit"


def test_evaluate_purged_funding_basis_no_future_leak():
    """Labels must not reference bars beyond the test window boundary.

    Every label's exit_idx must stay within its own test window.
    """
    closes = _make_closes(n=120)
    labels = evaluate_purged_funding_basis_walk_forward(closes, period=5, test_window=10, embargo=1)
    for label in labels:
        test_start = label["test_start"]
        test_end = label["test_end"]
        assert test_start <= label["entry_idx"] <= test_end, (
            f"entry_idx {label['entry_idx']} not in [{test_start},{test_end}]"
        )
        assert test_start <= label["exit_idx"] <= test_end, (
            f"label exit_idx {label['exit_idx']} not in [{test_start},{test_end}]"
        )
        assert label["exit_idx"] < len(closes), (
            f"label exit_idx {label['exit_idx']} exceeds closes length {len(closes)}"
        )


def test_evaluate_purged_funding_basis_raises_on_invalid_period():
    """Invalid period must raise ValueError."""
    closes = _make_closes(n=20)
    with pytest.raises(ValueError):
        evaluate_purged_funding_basis_walk_forward(closes, period=0, test_window=10, embargo=1)


def test_evaluate_purged_funding_basis_empty_on_insufficient_data():
    """Not enough bars for the holding period => no labels."""
    closes = [100.0, 101.0, 102.0]
    labels = evaluate_purged_funding_basis_walk_forward(closes, period=5, test_window=10, embargo=1)
    assert labels == []


def test_evaluate_purged_funding_basis_purge_guard_binds():
    """The purged guard must actually bind: if the loop allowed
    i + period > test_end, labels would leak past the window boundary.

    This test verifies that the purged constraint excludes labels
    whose exit would cross the test window boundary. If the guard
    were removed, labels with exit_idx > test_end would appear.
    """
    closes = _make_closes(n=120)
    labels = evaluate_purged_funding_basis_walk_forward(closes, period=5, test_window=10, embargo=1)
    for label in labels:
        assert label["exit_idx"] <= label["test_end"], (
            f"purge guard failed: exit_idx {label['exit_idx']} > test_end {label['test_end']}"
        )
