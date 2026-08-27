"""Measurement-only evaluation across a real multi-symbol candidate family.

Strengthens walk-forward evaluation (cron focus #2) by running the SAME
cost-inclusive, walk-forward, robustness-gated engine over several independent
real public datasets (a multi-symbol candidate family) and then applying the
Bonferroni family-wise multiple-testing correction from phase 11 across that
whole family.

A naive pipeline would scan many symbols/datasets and call any single
spuriously-positive window "edge". This orchestrator reports how many
candidates look positive BEFORE versus AFTER the family-wise correction, so a
lone lucky survivor among negatives cannot hide.

This is MEASUREMENT ONLY. ``selection_blocked`` is always True and no
``promoted``/``selected``/``winner`` key is ever emitted, so it stays
compatible with the always-blocked Phase 6 selection policy.
"""
import pytest
from pathlib import Path

from src.evaluation.baseline import (
    BaselineConfig,
    BaselineResult,
    evaluate_candidate_family,
)


def _fake_baseline(net_pnl, trade_pnls, closed_trades=len if False else 40):
    rows = []
    return BaselineResult(
        snapshots=100, network_calls=0, signed_calls=0, orders=0,
        closed_trades=closed_trades, open_positions=0, end_of_replay_closes=0,
        protection_attachments=0, reconciliation_checks=0, fees=0.0, spread=0.0,
        slippage=0.0, funding=0.0, gross_pnl=net_pnl, net_pnl=net_pnl,
        strategy_breakdown={}, regime_breakdown={}, walk_forward_splits=(),
        trade_pnls=tuple(trade_pnls),
    )


def _fake_window(net_pnl, closed_trades):
    return {"test_snapshots": 10, "closed_trades": closed_trades,
            "net_pnl": net_pnl, "fees": 0.0, "funding": 0.0,
            "slippage": 0.0, "spread": 0.0,
            "protection_attachments": closed_trades, "reconciliation_checks": 0,
            "strategy_breakdown": {}}


@pytest.fixture
def positive_candidates(monkeypatch):
    """Two clearly-positive candidates isolated from the heavy replay engine."""
    def fake_baseline(snapshots, config=None, **kw):
        return _fake_baseline(2000.0, [10.0] * 200, closed_trades=200)
    def fake_wf(snapshots, config=None, **kw):
        return (_fake_window(2000.0, 200),)
    monkeypatch.setattr("src.evaluation.baseline.run_baseline", fake_baseline)
    monkeypatch.setattr("src.evaluation.baseline.run_walk_forward", fake_wf)
    return [("symA", []), ("symB", [])]


@pytest.fixture
def negative_candidates(monkeypatch):
    def fake_baseline(snapshots, config=None, **kw):
        return _fake_baseline(-100.0, [-5.0] * 40, closed_trades=40)
    def fake_wf(snapshots, config=None, **kw):
        return (_fake_window(-100.0, 40),)
    monkeypatch.setattr("src.evaluation.baseline.run_baseline", fake_baseline)
    monkeypatch.setattr("src.evaluation.baseline.run_walk_forward", fake_wf)
    return [("symA", []), ("symB", []), ("symC", [])]


@pytest.fixture
def inadequate_candidates(monkeypatch):
    """Two candidates, but each has too few closed trades to clear the gate."""
    def fake_baseline(snapshots, config=None, **kw):
        return _fake_baseline(-50.0, [-5.0] * 10, closed_trades=10)
    def fake_wf(snapshots, config=None, **kw):
        return (_fake_window(-50.0, 10),)
    monkeypatch.setattr("src.evaluation.baseline.run_baseline", fake_baseline)
    monkeypatch.setattr("src.evaluation.baseline.run_walk_forward", fake_wf)
    return [("symA", []), ("symB", [])]


def test_evaluate_candidate_family_rejects_empty():
    with pytest.raises(ValueError, match="candidate"):
        evaluate_candidate_family([])


def test_evaluate_candidate_family_runs_per_candidate_and_aggregates(positive_candidates):
    out = evaluate_candidate_family(positive_candidates)
    assert out["candidates"] == 2
    assert len(out["per_candidate"]) == 2
    for cand in out["per_candidate"]:
        assert cand["name"] in ("symA", "symB")
        # Per-candidate gate is the NAIVE (uncorrected) verdict: positive here.
        assert cand["expectancy_positive_with_ci"] is True
    # Family-wise aggregation is present and computed over both candidates.
    fw = out["family_wise"]
    assert fw["tests"] == 2
    assert fw["correction"] == "bonferroni"
    # With only 2 candidates and a clearly positive edge, even the corrected
    # verdict survives (true edge is not over-rejected).
    assert fw["any_corrected_positive"] is True
    assert fw["corrected_positives"] == 2


def test_evaluate_candidate_family_never_promotes(negative_candidates):
    out = evaluate_candidate_family(negative_candidates)
    assert out["candidates"] == 3
    # Every naive candidate reads negative; family-wise correction agrees.
    assert out["family_wise"]["any_uncorrected_positive"] is False
    assert out["family_wise"]["any_corrected_positive"] is False
    assert out["family_wise"]["corrected_positives"] == 0
    # Measurement only: never promotes a strategy.
    assert out["selection_blocked"] is True
    assert "promoted" not in out and "selected" not in out and "winner" not in out
    assert "promoted" not in out["family_wise"]


def test_evaluate_candidate_family_reports_family_adequate_sample(positive_candidates):
    # Both candidates carry an adequate sample (200 closed trades each) so the
    # whole family clears the adequate-sample gate and the totals aggregate.
    out = evaluate_candidate_family(positive_candidates)
    assert out["total_closed_trades"] == 400
    assert out["family_adequate_sample"] is True


def test_evaluate_candidate_family_family_adequate_false_when_any_inadequate(inadequate_candidates):
    # A family scan must not read as "robust" if any member lacks an adequate
    # sample: a lone well-sampled survivor cannot launder a thin one.
    out = evaluate_candidate_family(inadequate_candidates)
    assert out["family_adequate_sample"] is False
    assert out["total_closed_trades"] == 20


def test_evaluate_candidate_family_real_stored_dataset_offline():
    # Integration path with the real replay engine on a durable stored dataset.
    # Asserts the function wires the real walk-forward + robustness gate without
    # depending on the (honestly negative) profitability of the data.
    path = Path("data/history/BTCUSDT_1m.json")
    if not path.exists():
        pytest.skip("stored dataset unavailable")
    from src.market.history import load_dataset, snapshots_from_dataset
    ds = load_dataset(path)
    snapshots = snapshots_from_dataset(ds)[:600]  # bound replay cost; still exercises real engine
    out = evaluate_candidate_family([("BTCUSDT_1m", snapshots)],
                                    BaselineConfig(real_funding=True))
    assert out["candidates"] == 1
    assert len(out["per_candidate"]) == 1
    gate = out["per_candidate"][0]
    assert "expectancy_positive_with_ci" in gate
    assert gate["total_closed_trades"] >= 0
    assert out["family_wise"]["tests"] == 1
    assert out["selection_blocked"] is True
    assert "promoted" not in out
