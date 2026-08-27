"""Fail-closed flat-line (constant derived-metric series) honesty check.

Build-verification lesson: a derived metric that never varies is WORSE than no
metric -- it launders silence as a result (e.g. `conviction=0.0` across every
snapshot). The report-honesty guard must therefore flag any numeric series
embedded in an evaluation / dashboard report that is entirely constant over a
sufficient window, so such a dead metric cannot be presented as a live finding.

Separate from the promotion/selection/verdict overclaims: this is the
"suspect constant series" layer. It is fail-closed (raises) so report writers
and dashboard projections cannot emit a dead metric as if it were signalling.
"""
import pytest

from src.evaluation.report_honesty import (
    ReportHonestyError,
    assert_no_suspect_constant_series,
    find_suspect_constant_series,
)


def test_flatline_detector_flags_constant_zero_series():
    report = {"conviction_series": [0.0, 0.0, 0.0, 0.0]}
    suspects = find_suspect_constant_series(report)
    assert len(suspects) == 1
    assert "conviction_series" in suspects[0]


def test_flatline_detector_flags_constant_nonzero_series():
    # Constant 1.0 (e.g. a mis-normalized persistence score) is equally suspect.
    report = {"persistence_scores": [1.0, 1.0, 1.0]}
    suspects = find_suspect_constant_series(report)
    assert len(suspects) == 1
    assert "persistence_scores" in suspects[0]


def test_flatline_detector_flags_constant_integer_series():
    report = {"signal_hits": [3, 3, 3, 3, 3]}
    suspects = find_suspect_constant_series(report)
    assert len(suspects) == 1


def test_flatline_detector_ignores_varied_series():
    report = {"conviction_series": [0.0, 0.1, 0.0, 0.2]}
    assert find_suspect_constant_series(report) == []


def test_flatline_detector_ignores_short_series():
    # Below the minimum sample window a constant list is not yet a flat-line claim.
    report = {"conviction_series": [0.0, 0.0]}
    assert find_suspect_constant_series(report) == []


def test_flatline_detector_ignores_non_numeric_lists():
    report = {"labels": ["a", "a", "a", "a"]}
    assert find_suspect_constant_series(report) == []


def test_flatline_detector_recurses_into_nested_dicts():
    report = {"metrics": {"window_scores": [2.0, 2.0, 2.0]}}
    suspects = find_suspect_constant_series(report)
    assert len(suspects) == 1
    assert "window_scores" in suspects[0]


def test_flatline_detector_recurses_into_lists_of_dicts():
    report = [{"conviction_series": [0.0, 0.0, 0.0]}]
    suspects = find_suspect_constant_series(report)
    assert len(suspects) == 1


def test_flatline_detector_respects_custom_min_samples():
    report = {"conviction_series": [0.0, 0.0, 0.0, 0.0, 0.0]}
    # With a higher threshold the 5-long series is below the bar.
    assert find_suspect_constant_series(report, min_samples=6) == []
    # With the default (3) it is flagged.
    assert len(find_suspect_constant_series(report)) == 1


def test_assert_no_suspect_constant_series_raises_on_flatline():
    report = {"conviction_series": [0.0, 0.0, 0.0]}
    with pytest.raises(ReportHonestyError):
        assert_no_suspect_constant_series(report)


def test_assert_no_suspect_constant_series_allows_varied():
    report = {"conviction_series": [0.0, 0.1, 0.0]}
    assert_no_suspect_constant_series(report)  # does not raise


def test_assert_no_suspect_constant_series_allows_honest_baseline_payload():
    # The genuine, un-tampered baseline payload must not carry a dead metric.
    from scripts.run_strategy_baseline import make_series
    from src.evaluation.baseline import run_baseline, run_walk_forward, run_cost_stress
    from src.evaluation.stress import run_stress_matrix
    from src.evaluation.statistics import compute_statistics

    series = make_series()
    result = run_baseline(series)
    payload = dict(result.__dict__)
    payload["walk_forward_evaluation"] = run_walk_forward(series)
    payload["cost_stress"] = run_cost_stress(series)
    payload["stress_matrix"] = run_stress_matrix(series)
    payload["statistics"] = compute_statistics(result.trade_pnls)
    payload["selection_blocked"] = True

    assert_no_suspect_constant_series(payload)  # does not raise
