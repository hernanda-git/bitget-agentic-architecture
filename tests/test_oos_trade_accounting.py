"""Regression test for strict OOS trade-level robustness accounting."""
from types import SimpleNamespace

import src.evaluation.baseline as baseline_module


def _oos_rows():
    return (
        {"closed_trades": 2, "gross_pnl": 2.0, "fees": 0.0, "funding": 0.0,
         "spread": 0.0, "slippage": 0.0, "net_pnl": 2.0,
         "trade_pnls": [1.0, 1.0], "strategy_breakdown": {}},
    )


def test_candidate_family_robustness_uses_only_oos_trade_pnls(monkeypatch):
    """Train-period losses must not contaminate the OOS expectancy CI input."""
    fake_baseline = SimpleNamespace(
        trade_pnls=(-100.0, -100.0),  # deliberately contradictory train/full replay values
        net_pnl=-200.0,
        closed_trades=2,
        gross_pnl=-200.0,
        fees=0.0,
        funding=0.0,
        spread=0.0,
        slippage=0.0,
        strategy_breakdown={},
        regime_breakdown={},
    )
    monkeypatch.setattr(baseline_module, "run_baseline", lambda snapshots, config: fake_baseline)
    monkeypatch.setattr(baseline_module, "run_walk_forward", lambda snapshots, config: _oos_rows())

    observed = {}
    original_gate = baseline_module.gate_walk_forward_robustness

    def capture_gate(rows, **kwargs):
        observed["trade_pnls"] = tuple(kwargs.get("trade_pnls", ()))
        return original_gate(rows, **kwargs)

    monkeypatch.setattr(baseline_module, "gate_walk_forward_robustness", capture_gate)
    result = baseline_module.evaluate_candidate_family(
        (("candidate", (object(),)),), min_closed_trades=1
    )

    assert observed["trade_pnls"] == (1.0, 1.0)
    assert result["per_candidate"][0]["expectancy_mean"] == 1.0
