"""Factor-ontology coverage gate (Phase 45, TDD).

The Autonomous Bitcoin Adaptation Directive sec. 3 defines a living factor
ontology across seven categories. This test makes that ontology machine-readable
and binds it to the hypothesis registry so coverage gaps are visible and
promotion cannot be claimed while whole categories remain unrepresented.
"""
import pytest

from src.evaluation.factor_ontology import (
    FACTOR_CATEGORIES,
    FactorOntologyError,
    normalize_category,
    coverage_summary,
)
from src.evaluation.hypotheses import Hypothesis, HypothesisRegistry

DIRECTIVE_CATEGORIES = {
    "macro_liquidity",
    "onchain",
    "derivatives_microstructure",
    "flow_participation",
    "sentiment_attention",
    "time_structure",
    "adversarial",
}


def test_ontology_mirrors_directive_seven_categories():
    # The canonical mirror must contain exactly the seven directive sec.3 categories.
    assert set(FACTOR_CATEGORIES.keys()) == DIRECTIVE_CATEGORIES
    # Every category must enumerate at least one concrete factor (no empty buckets).
    assert all(len(factors) >= 1 for factors in FACTOR_CATEGORIES.values())


def test_normalize_category_is_strict_and_rejects_unknown():
    # Each known canonical key normalizes to itself (no silent aliasing of bad input).
    for key in FACTOR_CATEGORIES:
        assert normalize_category(key) == key
    # Unknown categories must fail closed, never be coerced into a real bucket.
    with pytest.raises(FactorOntologyError):
        normalize_category("not_a_real_category")


def test_hypothesis_requires_known_factor_category():
    good = Hypothesis(
        hypothesis_id="H-001", title="Trend persistence", mechanism="momentum persists",
        data="offline candle history", features=("momentum",), category="time_structure",
        entry_exit="enter on breakout; exit at stop/target",
        cost_edge="move exceeds fees, spread and slippage", falsification="negative net PnL OOS",
        failure_modes="chop and stale data", data_exclusions="duplicates and incomplete windows",
        oos_gate="walk-forward positive net PnL with minimum sample",
    )
    good.validate()  # must not raise
    # An otherwise fully-populated hypothesis with an unknown category must be rejected
    # (isolates the category rule from the required-field rule).
    fully_populated = dict(
        hypothesis_id="bad", title="x", mechanism="m", data="d", features=("f",),
        entry_exit="e", cost_edge="c", falsification="f", failure_modes="fm",
        data_exclusions="de", oos_gate="og",
    )
    with pytest.raises(ValueError):
        Hypothesis(category="made_up_category", **fully_populated).validate()
    with pytest.raises(ValueError):
        Hypothesis(category="", **fully_populated).validate()


def test_registry_coverage_gate_exposes_unrepresented_categories():
    registry = HypothesisRegistry()
    registry.register(
        Hypothesis(
            hypothesis_id="H-001", title="Trend persistence", mechanism="momentum persists",
            data="offline candle history", features=("momentum",), category="time_structure",
            entry_exit="enter on breakout; exit at stop/target",
            cost_edge="move exceeds fees, spread and slippage", falsification="negative net PnL OOS",
            failure_modes="chop and stale data", data_exclusions="duplicates and incomplete windows",
            oos_gate="walk-forward positive net PnL with minimum sample",
        )
    )
    summary = coverage_summary(registry)
    assert summary["represented_count"] == 1
    assert summary["represented_categories"] == ["time_structure"]
    # Six of the seven directive categories are still uncovered by any hypothesis.
    assert summary["unrepresented_count"] == 6
    assert "macro_liquidity" in summary["unrepresented_categories"]
    # Fail closed: a single covered category is NOT promotion-ready.
    assert summary["promotion_ready"] is False


def test_coverage_gate_is_fail_closed_on_empty_registry():
    summary = coverage_summary(HypothesisRegistry())
    assert summary["represented_count"] == 0
    assert summary["unrepresented_count"] == 7
    assert summary["promotion_ready"] is False


def test_coverage_gate_turns_ready_only_when_all_seven_represented():
    registry = HypothesisRegistry()
    for i, cat in enumerate(sorted(DIRECTIVE_CATEGORIES)):
        registry.register(
            Hypothesis(
                hypothesis_id=f"H-{100 + i}", title=f"claim for {cat}", mechanism="mechanism",
                data="offline candle history", features=("f",), category=cat,
                entry_exit="enter; exit at stop/target",
                cost_edge="move exceeds all costs", falsification="negative net PnL OOS",
                failure_modes="chop", data_exclusions="duplicates",
                oos_gate="walk-forward positive net PnL",
            )
        )
    summary = coverage_summary(registry)
    assert summary["represented_count"] == 7
    assert summary["unrepresented_count"] == 0
    assert summary["represented_categories"] == sorted(DIRECTIVE_CATEGORIES)
    assert summary["promotion_ready"] is True
