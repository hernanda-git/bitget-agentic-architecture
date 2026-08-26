"""Multiple-testing correction for the walk-forward robustness gate.

Strengthens walk-forward evaluation (cron focus #2) against the family-wise
error problem: the pipeline implicitly scans many candidate "edges" (3
strategies x 4 datasets), so a single spuriously-positive window can masquerade
as real edge if every test is judged at the same naive 0.95 level.

A Bonferroni-adjusted confidence level tightens the CI lower bound when a gate is
one of ``n_tests`` simultaneous tests, so a lucky positive window can no longer
flip the verdict. This is conservative (fail closed) and never promotes:
``selection_blocked`` stays True in every path.

This is MEASUREMENT ONLY. It never changes the deterministic promotion gate
(NEGATIVE_NET_PNL) and never emits a promoted/selected/winner flag.
"""
import pytest
from statistics import mean

from src.evaluation.baseline import (
    family_wise_robustness,
    gate_walk_forward_robustness,
)


def _window(net_pnl, closed_trades=5):
    return {
        "train_start": 0, "train_end": 9, "test_start": 10, "test_end": 19,
        "context_start": 0, "context_end": 9, "test_snapshots": 10,
        "closed_trades": closed_trades, "gross_pnl": net_pnl,
        "protection_attachments": closed_trades, "reconciliation_checks": 0,
        "fees": 0.0, "funding": 0.0, "slippage": 0.0, "net_pnl": net_pnl,
        "spread": 0.0, "strategy_breakdown": {},
    }


def test_bonferroni_tightens_ci_and_flips_a_lucky_positive_window():
    # A "lucky" strategy: 200 trades, mean +5.0, but wide enough spread that the
    # naive 95% CI lower bound is slightly positive while the family-wise
    # corrected CI lower bound (one of 20 simultaneous tests) drops below zero.
    lucky_pnls = [31.0] * 100 + [-21.0] * 100  # mean = +5.0
    rows = [_window(5.0, closed_trades=200)]

    naive = gate_walk_forward_robustness(rows, trade_pnls=lucky_pnls, n_tests=1)
    corrected = gate_walk_forward_robustness(rows, trade_pnls=lucky_pnls, n_tests=20)

    # The naive test wrongly looks like proven positive expectancy.
    assert naive["expectancy_mean"] > 0
    assert naive["expectancy_ci"][0] > 0
    assert naive["expectancy_positive_with_ci"] is True

    # After family-wise correction the same window no longer clears the bar.
    assert corrected["expectancy_ci"][0] <= 0
    assert corrected["expectancy_positive_with_ci"] is False

    # Measurement only: correction never promotes a strategy.
    assert naive["selection_blocked"] is True
    assert corrected["selection_blocked"] is True


def test_n_tests_one_reproduces_naive_behavior():
    rows = [_window(120.0, closed_trades=40), _window(80.0, closed_trades=40)]
    trade_pnls = [10.0, 12.0, -5.0, 8.0, 15.0, 3.0] * 40
    default = gate_walk_forward_robustness(rows, trade_pnls=trade_pnls)
    explicit = gate_walk_forward_robustness(rows, trade_pnls=trade_pnls, n_tests=1)
    assert explicit["expectancy_ci"] == default["expectancy_ci"]
    assert explicit["expectancy_positive_with_ci"] == default["expectancy_positive_with_ci"]


def test_n_tests_below_one_is_rejected():
    rows = [_window(120.0, closed_trades=40)]
    with pytest.raises(ValueError, match="n_tests"):
        gate_walk_forward_robustness(rows, n_tests=0)
    with pytest.raises(ValueError, match="n_tests"):
        gate_walk_forward_robustness(rows, n_tests=-3)


def test_family_wise_correction_catches_the_lucky_strategy_among_negatives():
    # 19 clearly negative candidate edges + 1 lucky positive window. Without a
    # correction the lucky window would read as proven positive expectancy.
    lucky_pnls = [31.0] * 100 + [-21.0] * 100
    tests = [
        {"rows": [_window(-100.0, closed_trades=40)], "trade_pnls": [-5.0] * 40}
        for _ in range(19)
    ]
    tests.append({"rows": [_window(5.0, closed_trades=200)], "trade_pnls": lucky_pnls})

    out = family_wise_robustness(tests, alpha=0.05)

    assert out["tests"] == 20
    assert out["correction"] == "bonferroni"
    assert out["family_wise_alpha"] == 0.05
    # Naive scanning would have promoted the lucky window.
    assert out["any_uncorrected_positive"] is True
    assert out["uncorrected_positives"] == 1
    # Family-wise correction rejects it.
    assert out["any_corrected_positive"] is False
    assert out["corrected_positives"] == 0
    # Never promotes.
    assert out["selection_blocked"] is True
    assert "promoted" not in out and "selected" not in out


def test_family_wise_stays_blocked_on_all_negative_family():
    tests = [
        {"rows": [_window(-100.0, closed_trades=40)], "trade_pnls": [-5.0] * 40}
        for _ in range(12)
    ]
    out = family_wise_robustness(tests)
    assert out["any_uncorrected_positive"] is False
    assert out["any_corrected_positive"] is False
    assert out["selection_blocked"] is True


def test_family_wise_does_not_over_reject_true_edge():
    # A genuinely strong, low-variance edge must survive correction.
    strong_pnls = [10.0] * 200  # mean +10, zero variance
    tests = [{"rows": [_window(200.0, closed_trades=200)], "trade_pnls": strong_pnls}]
    out = family_wise_robustness(tests, alpha=0.05)
    assert out["any_uncorrected_positive"] is True
    assert out["any_corrected_positive"] is True
    assert out["selection_blocked"] is True


def test_family_wise_rejects_empty():
    with pytest.raises(ValueError, match="family"):
        family_wise_robustness([])


def test_family_wise_requires_consensus_across_strategies_flag():
    # The aggregation also reports how many candidate edges would have passed
    # naive versus corrected scanning, so a lone survivor cannot hide.
    # The lucky distribution must sit where the naive 95% CI is clearly positive
    # but the family-wise (k=8, ~99.4%) CI lower bound crosses zero; [31]/[-21]
    # lands right on the boundary and does not flip, so we use a clearly-extreme
    # lucky window ([40]/[-30]) to demonstrate the correction honestly.
    lucky_pnls = [40.0] * 100 + [-30.0] * 100
    tests = [
        {"rows": [_window(-50.0, closed_trades=40)], "trade_pnls": [-4.0] * 40}
        for _ in range(5)
    ] + [
        {"rows": [_window(5.0, closed_trades=200)], "trade_pnls": lucky_pnls}
        for _ in range(3)
    ]
    out = family_wise_robustness(tests)
    assert out["tests"] == 8
    assert out["uncorrected_positives"] == 3
    assert out["corrected_positives"] == 0
    assert out["any_corrected_positive"] is False
