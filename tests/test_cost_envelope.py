"""Full cost sensitivity envelope: independent fee/funding/slippage grid (TDD).

The existing cost-stress stack scales ALL costs together by one multiplier
(`cost_sensitivity_sweep`, `run_cost_stress`) or raises them one dimension at a
time (`run_stress_matrix`, `run_combined_stress`). None of them sweeps the
independent combinations of fee / funding / slippage as a grid and reports the
FULL sensitivity envelope (min / max / median net PnL and the worst cell).

This suite covers `cost_envelope_sweep`, which closes that gap. It is
measurement-only: it never changes the deterministic promotion gate and always
emits `selection_blocked=True` / `promotion_blocked=True`. No winner / promoted
/ selected / positive-edge key is ever produced.
"""
from __future__ import annotations
from unittest.mock import patch

import pytest

from src.evaluation.baseline import BaselineConfig
from scripts.run_strategy_baseline import make_series


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n % 2 == 1:
        return xs[n // 2]
    return (xs[n // 2 - 1] + xs[n // 2]) / 2


def test_module_and_function_exist():
    """RED anchor: the envelope function must exist on the cost-sensitivity module."""
    from src.evaluation import cost_sensitivity
    assert hasattr(cost_sensitivity, "cost_envelope_sweep")


def test_rejects_empty_snapshots():
    from src.evaluation.cost_sensitivity import cost_envelope_sweep
    with pytest.raises(ValueError):
        cost_envelope_sweep((), BaselineConfig())


def test_rejects_negative_multiplier():
    from src.evaluation.cost_sensitivity import cost_envelope_sweep
    with pytest.raises(ValueError):
        cost_envelope_sweep(make_series(), BaselineConfig(), fee_mults=(1.0, -1.0))


def test_rejects_nonfinite_multiplier():
    from src.evaluation.cost_sensitivity import cost_envelope_sweep
    with pytest.raises(ValueError):
        cost_envelope_sweep(make_series(), BaselineConfig(), slippage_mults=(1.0, float("nan")))


def test_envelope_cell_count_and_no_invented_trades():
    """Grid size is the product of the three ladders; no cell may invent trades
    versus the baseline, and the baseline cell must match the explicit baseline."""
    from src.evaluation.cost_sensitivity import cost_envelope_sweep
    cfg = BaselineConfig()
    series = make_series()
    fee = (0.5, 1.0, 1.5)
    fund = (0.5, 1.0)
    slip = (0.5, 1.0, 2.0)
    res = cost_envelope_sweep(series, cfg, fee_mults=fee, funding_mults=fund, slippage_mults=slip)
    assert res["n_cells"] == len(fee) * len(fund) * len(slip)
    assert len(res["cells"]) == res["n_cells"]
    for cell in res["cells"]:
        assert cell["closed_trades"] <= res["baseline_closed_trades"]
    # envelope ordering is internally consistent
    assert res["min_net"] <= res["median_net"] + 1e-9
    assert res["median_net"] <= res["max_net"] + 1e-9
    # baseline cell (all 1.0) equals the explicit baseline result
    base = res["baseline_net"]
    cell10 = next(c for c in res["cells"]
                  if c["fee_mult"] == 1.0 and c["funding_mult"] == 1.0 and c["slippage_mult"] == 1.0)
    assert cell10["net_pnl"] == pytest.approx(base, rel=1e-9)
    # every cell carries drawdown (non-negative) and the cost fields
    for cell in res["cells"]:
        assert cell["drawdown"] >= 0.0
        for k in ("fee_mult", "funding_mult", "slippage_mult", "fee_bps", "funding_bps",
                  "slippage_bps", "net_pnl", "gross_pnl", "fees", "funding", "spread", "slippage"):
            assert k in cell


def test_envelope_worst_cell_is_min_and_best_is_max():
    from src.evaluation.cost_sensitivity import cost_envelope_sweep
    cfg = BaselineConfig()
    res = cost_envelope_sweep(make_series(), cfg, fee_mults=(0.5, 1.0, 2.0),
                              funding_mults=(0.5, 1.0, 2.0), slippage_mults=(0.5, 1.0, 2.0))
    nets = [c["net_pnl"] for c in res["cells"]]
    assert res["min_net"] == pytest.approx(min(nets))
    assert res["max_net"] == pytest.approx(max(nets))
    assert res["worst_cell"]["net_pnl"] == pytest.approx(res["min_net"])
    assert res["best_cell"]["net_pnl"] == pytest.approx(res["max_net"])


def test_envelope_selection_always_blocked():
    """The envelope is measurement only: it must never emit a promotion/winner
    verdict and must keep the Phase 6 gate blocked."""
    from src.evaluation.cost_sensitivity import cost_envelope_sweep
    res = cost_envelope_sweep(make_series(), BaselineConfig())
    assert res["promotion_blocked"] is True
    assert res["selection_blocked"] is True
    # the synthetic series is negative even at zero scalable cost, so the whole
    # envelope is blocked
    assert res["all_blocked"] is True
    for forbidden in ("winner", "promoted", "selected", "go_live", "positive_edge"):
        assert forbidden not in res


def test_envelope_any_profitable_flag_with_fake_engine():
    """Positive control for the aggregation + any_profitable flag. A fake engine
    (not a fake of the SUT) yields positive net at low cost and negative at high,
    exercising the envelope math without touching real market data."""
    from src.evaluation.baseline import BaselineResult
    from src.evaluation.cost_sensitivity import cost_envelope_sweep
    cfg = BaselineConfig()  # fee_bps = 5.0
    captured = {}

    def fake_engine(snapshots, scaled):
        m = scaled.fee_bps / cfg.fee_bps  # recover the fee multiplier
        captured.setdefault("mults", set()).add(round(m, 3))
        net = 100.0 - 150.0 * m
        return BaselineResult(
            snapshots=len(snapshots), network_calls=0, signed_calls=0, orders=0,
            closed_trades=10, open_positions=0, end_of_replay_closes=0,
            protection_attachments=0, reconciliation_checks=0,
            fees=0.0, spread=0.0, slippage=0.0, funding=0.0, gross_pnl=0.0,
            net_pnl=net, strategy_breakdown={}, regime_breakdown={},
            walk_forward_splits=(),
        )

    with patch("src.evaluation.cost_sensitivity.run_baseline", fake_engine):
        res = cost_envelope_sweep(make_series(), cfg, fee_mults=(0.25, 1.0, 3.0),
                                  funding_mults=(1.0,), slippage_mults=(1.0,))
    assert res["any_profitable"] is True
    assert res["all_blocked"] is False
    assert res["selection_blocked"] is True
    assert res["promotion_blocked"] is True
    assert res["min_net"] < res["max_net"]
    assert 1.0 in captured["mults"]


def test_envelope_on_real_history_reports_full_block_and_envelope():
    """Honest real-shaped demonstration: run the envelope over already-local
    public BTCUSDT 1m history (no network egress). It must report the full
    envelope fields and stay fully blocked."""
    from pathlib import Path
    from src.market.history import load_dataset, snapshots_from_dataset
    from src.evaluation.cost_sensitivity import cost_envelope_sweep
    snapshots = snapshots_from_dataset(load_dataset(Path("data/history/BTCUSDT_1m.json")))[:600]
    cfg = BaselineConfig(real_funding=False)
    res = cost_envelope_sweep(snapshots, cfg, fee_mults=(1.0, 2.0),
                              funding_mults=(1.0, 2.0), slippage_mults=(1.0, 2.0))
    assert res["selection_blocked"] is True
    assert res["promotion_blocked"] is True
    assert res["n_cells"] == 8
    # honest: on real history the envelope is negative across the whole grid
    assert res["any_profitable"] is False
    assert res["all_blocked"] is True
    assert res["min_net"] < 0
    assert res["max_net"] <= 0  # even the best grid point stays <= 0 here
    # envelope extremes are consistent with the cells
    nets = [c["net_pnl"] for c in res["cells"]]
    assert res["min_net"] == pytest.approx(min(nets))
    assert res["max_net"] == pytest.approx(max(nets))
