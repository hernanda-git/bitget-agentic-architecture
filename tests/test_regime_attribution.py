"""Regime-conditioned strategy attribution (TDD: RED first).

The existing ``attribute_performance`` decomposes measured per-strategy returns
only by strategy *family*. It never answers the honest-edge question the rest of
the evaluation stack cares about: *is the edge concentrated in one market
regime?* A strategy whose positive aggregate comes entirely from one regime is
fragile, and a lone lucky regime can launder a spurious edge through the
cross-sectional dispersion check.

This module adds ``attribute_performance_by_regime``, which slices the SAME
aligned per-step return stream by an externally supplied regime label per
timestep (produced by ``src.strategies.regime.classify_regime`` in the real
pipeline) and reports, fail-closed and descriptively:

* per-regime equal-weight blend expectancy + bootstrap CI + sample size
* per-strategy / per-regime expectancy matrix
* edge concentration: which regime carries the most |net| and its share

It never emits a winner / promotion / selection flag and ``selection_blocked``
is always ``True``, so it cannot change the deterministic Phase 6 promotion
gate (which stays blocked in this repository). No network, no credentials, no
signed calls, no orders.

Pure offline measurement: ``regime_labels`` are an injected input so the
attribution logic is testable without a market feed.
"""
from __future__ import annotations

import pytest

from src.evaluation import attribution


def _aligned(strat_returns, regimes):
    return attribution.attribute_performance_by_regime(strat_returns, regimes)


# regimes aligned to a 6-step shared timestep index
_REGIMES = ["TRENDING", "RANGING", "TRENDING", "RANGING", "TRENDING", "RANGING"]
_STRAT = {
    "momentum": [0.01, -0.005, 0.02, -0.01, 0.015, -0.004],
    "mean_rev": [-0.008, 0.012, -0.01, 0.018, -0.006, 0.02],
}


def test_attribution_by_regime_decomposes_per_regime_expectancy():
    """Blend expectancy per regime equals the mean of all aligned returns in that regime."""
    report = _aligned(_STRAT, _REGIMES)

    # TRENDING steps (idx 0,2,4): momentum 0.01/0.02/0.015, mean_rev -0.008/-0.01/-0.006
    #   blend mean = (0.045 - 0.024) / 6 = 0.0035
    # RANGING steps (idx 1,3,5): momentum -0.005/-0.01/-0.004, mean_rev 0.012/0.018/0.02
    #   blend mean = (-0.019 + 0.05) / 6 = 0.0051667
    assert report["regimes"]["TRENDING"]["expectancy"] == pytest.approx(0.0035)
    assert report["regimes"]["RANGING"]["expectancy"] == pytest.approx(0.0051667, rel=1e-4)

    # Per-strategy / per-regime matrix is exact.
    assert report["strategies"]["momentum"]["TRENDING"]["expectancy"] == pytest.approx(0.015)
    assert report["strategies"]["momentum"]["RANGING"]["expectancy"] == pytest.approx(-0.0063333, rel=1e-4)
    assert report["strategies"]["mean_rev"]["TRENDING"]["expectancy"] == pytest.approx(-0.008)
    assert report["strategies"]["mean_rev"]["RANGING"]["expectancy"] == pytest.approx(0.0166667, rel=1e-4)

    # Sample sizes per strategy/regime reflect the aligned steps.
    assert report["strategies"]["momentum"]["TRENDING"]["n"] == 3
    assert report["strategies"]["mean_rev"]["RANGING"]["n"] == 3
    # The regime blend concatenates every strategy's return at the regime's
    # steps, so its n is steps_in_regime * n_strategies (3 steps * 2 = 6).
    assert report["regimes"]["TRENDING"]["n"] == 6
    assert report["regimes"]["RANGING"]["n"] == 6
    assert report["regimes"]["TRENDING"]["n_strategies"] == 2


def test_attribution_by_regime_reports_net_and_concentration():
    """Edge concentration identifies the regime carrying the most |net| contribution."""
    report = _aligned(_STRAT, _REGIMES)

    # net TRENDING = 0.021, net RANGING = 0.031 -> RANGING dominates by |net|.
    assert report["regimes"]["TRENDING"]["net"] == pytest.approx(0.021)
    assert report["regimes"]["RANGING"]["net"] == pytest.approx(0.031)

    conc = report["edge_concentration"]
    assert conc["dominant_regime"] == "RANGING"
    # share = 0.031 / (0.021 + 0.031) = 0.59615...
    assert conc["dominant_share_abs"] == pytest.approx(0.59615, rel=1e-3)
    # Both regimes show a positive blend expectancy in this constructed example.
    assert conc["regimes_with_positive_expectancy"] == 2

    # share_of_abs_net is exposed per regime for downstream dashboards.
    assert report["regimes"]["RANGING"]["share_of_abs_net"] == pytest.approx(0.59615, rel=1e-3)
    assert report["regimes"]["TRENDING"]["share_of_abs_net"] == pytest.approx(0.40385, rel=1e-3)


def test_attribution_by_regime_selection_always_blocked():
    """Descriptive only: never flips the deterministic promotion gate."""
    report = _aligned(_STRAT, _REGIMES)
    assert report["selection_blocked"] is True
    assert report["attribution_is_descriptive"] is True
    assert "promotion" not in report or report.get("promotion_allowed") in (False, None)
    # No winner label anywhere in the regimes sub-dicts.
    for r in report["regimes"].values():
        assert "winner" not in r
    # The honest-truthfulness forbidden keys must be absent.
    from src.evaluation.report_honesty import find_overclaims
    assert find_overclaims(report) == []


def test_attribution_by_regime_rejects_mismatched_alignment():
    """A regime label series that is not aligned to the return steps fails closed."""
    short_regimes = ["TRENDING", "RANGING", "TRENDING"]
    with pytest.raises(ValueError):
        attribution.attribute_performance_by_regime(_STRAT, short_regimes)


def test_attribution_by_regime_rejects_non_finite():
    """A non-finite return fails closed (never silently dropped)."""
    bad = {"momentum": [0.01, float("nan"), 0.02], "mean_rev": [-0.008, 0.012, -0.01]}
    regimes = ["TRENDING", "RANGING", "TRENDING"]
    with pytest.raises(ValueError):
        attribution.attribute_performance_by_regime(bad, regimes)


def test_attribution_by_regime_rejects_single_strategy():
    """Needs at least two strategies, matching the family-level attribution gate."""
    single = {"momentum": [0.01, -0.005, 0.02]}
    with pytest.raises(ValueError):
        attribution.attribute_performance_by_regime(single, _REGIMES[:3])


def test_attribution_by_regime_handles_degraded_regime_label():
    """A DATA_DEGRADED (or any sparse) regime is reported, not dropped or overclaimed."""
    regimes = ["TRENDING", "DATA_DEGRADED", "TRENDING", "RANGING", "TRENDING", "RANGING"]
    report = _aligned(_STRAT, regimes)
    assert "DATA_DEGRADED" in report["regimes"]
    # The regime appears at 1 step but across 2 strategies -> blend n = 2.
    assert report["regimes"]["DATA_DEGRADED"]["n"] == 2
    assert report["regimes"]["DATA_DEGRADED"]["n_strategies"] == 2
    # Blend expectancy is the cross-strategy mean at that step: (-0.005 + 0.012)/2.
    assert report["regimes"]["DATA_DEGRADED"]["expectancy"] == pytest.approx(0.0035)
    # Still descriptive and blocked (no overclaim even for a sparse regime).
    assert report["selection_blocked"] is True
    assert report["attribution_is_descriptive"] is True


def test_attribution_by_regime_bootstrap_ci_is_finite_pair():
    """Every regime blend carries a finite bootstrap CI pair for honest uncertainty."""
    report = _aligned(_STRAT, _REGIMES)
    for r in report["regimes"].values():
        ci = r["bootstrap_ci"]
        assert isinstance(ci, (list, tuple)) and len(ci) == 2
        assert all(__import__("math").isfinite(x) for x in ci)
