"""Keep/Kill outcome recording on the hypothesis registry (Phase 48, TDD).

The Autonomous Bitcoin Adaptation Directive sec. 5 defines the adaptation loop
``Observe -> Hypothesize -> Shadow-test -> Measure -> Keep/Kill -> Reconfigure`` and
sec. 7 demands "kill what doesn't -- without sentiment." The registry (Phase 46)
stores *hypotheses* but has no fail-closed way to record the measured verdict
(keep / kill / hold) with its evidence. This test binds that gap: every outcome is
evidenced, unknown hypotheses and unknown verdicts fail closed, and a kill cannot
be recorded without a stated reason.

The deterministic baseline is negative, so this is bookkeeping for the loop -- it
changes nothing about trading logic and never makes a promotion claim.
"""
import pytest

from src.evaluation.hypotheses import Hypothesis, HypothesisRegistry


def _valid_hypothesis(hypothesis_id="H-001", category="time_structure"):
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        title=f"claim for {category}",
        mechanism="momentum persists",
        data="offline candle history",
        features=("momentum",),
        category=category,
        entry_exit="enter on breakout; exit at stop/target",
        cost_edge="move exceeds fees, spread and slippage",
        falsification="negative net PnL OOS",
        failure_modes="chop and stale data",
        data_exclusions="duplicates and incomplete windows",
        oos_gate="walk-forward positive net PnL with minimum sample",
    )


def test_mark_outcome_records_verdict_reason_and_evidence():
    # A measured verdict must be retrievable verbatim, with its evidence.
    registry = HypothesisRegistry()
    registry.register(_valid_hypothesis("H-001"))
    registry.mark_outcome(
        "H-001", "keep", "survived walk-forward OOS", evidence="net PnL > 0 over 3 windows"
    )
    outcome = registry.outcome("H-001")
    assert outcome is not None
    assert outcome.verdict == "keep"
    assert outcome.reason == "survived walk-forward OOS"
    assert outcome.evidence == "net PnL > 0 over 3 windows"


def test_mark_outcome_rejects_unknown_hypothesis_fail_closed():
    # A verdict for a hypothesis that was never registered must never be stored.
    registry = HypothesisRegistry()
    registry.register(_valid_hypothesis("H-001"))
    with pytest.raises(ValueError):
        registry.mark_outcome("H-999", "keep", "reason")


def test_mark_outcome_rejects_invalid_verdict_fail_closed():
    # An unrecognized verdict (e.g. "maybe") must be rejected, never coerced.
    registry = HypothesisRegistry()
    registry.register(_valid_hypothesis("H-001"))
    with pytest.raises(ValueError):
        registry.mark_outcome("H-001", "maybe", "reason")
    # The verdict is also normalized to lowercase so "KILL" == "kill".
    registry.mark_outcome("H-001", "KILL", "negative OOS net PnL")
    assert registry.outcome("H-001").verdict == "kill"


def test_mark_outcome_requires_a_nonempty_reason():
    # Every verdict is a decision and must be evidenced; a kill especially so.
    registry = HypothesisRegistry()
    registry.register(_valid_hypothesis("H-001"))
    with pytest.raises(ValueError):
        registry.mark_outcome("H-001", "keep", "")
    with pytest.raises(ValueError):
        registry.mark_outcome("H-001", "kill", "   ")
    # A kill with a real reason is accepted (the honesty gate's core demand).
    registry.mark_outcome("H-001", "kill", "failed OOS gate, negative net PnL after costs")
    assert registry.outcome("H-001").verdict == "kill"


def test_outcomes_iterates_only_marked_hypotheses():
    # outcomes() yields exactly the hypotheses that received a verdict.
    registry = HypothesisRegistry()
    registry.register(_valid_hypothesis("H-001"))
    registry.register(_valid_hypothesis("H-002", category="onchain"))
    registry.mark_outcome("H-001", "keep", "survived")
    assert set(registry.outcomes().keys()) == {"H-001"}
    # Marking a second verdict extends, without clobbering the first.
    registry.mark_outcome("H-002", "hold", "insufficient sample")
    assert set(registry.outcomes().keys()) == {"H-001", "H-002"}
    assert registry.outcome("H-001").verdict == "keep"
    assert registry.outcome("H-002").verdict == "hold"
