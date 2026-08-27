"""Cost break-even sensitivity for the deterministic baseline (measurement only).

The baseline reports gross PnL (the raw strategy edge before costs) and net PnL
(after fee + spread + slippage + funding). This suite answers the honest operator
question: *how far would execution costs have to fall for this strategy to become
viable?* It does so with a fail-closed break-even analysis and NEVER emits a
promotion/winner/positive-verdict overclaim.

Test discipline note (TDD truthfulness): an earlier draft asserted that REAL
ETHUSDT history has a positive zero-cost net (gross edge above the assumed spread)
and therefore a break-even exists. The live engine over the stored public data
disagrees: at multiplier 0 the strategy takes ~649 trades and the assumed half-spread
(0.5 bps/trade) sums to ~160 bps of cost, while the gross edge is only ~78. The
zero-cost net is NEGATIVE, so no break-even exists on real history. The honest
result is ``has_break_even=False``. The positive control for the interpolation/verdict
MATH is therefore exercised on synthetic rows and a fake engine, never by
overclaiming about real market data.
"""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from src.evaluation.baseline import BaselineConfig, BaselineResult, run_baseline
from src.evaluation.cost_sensitivity import (
    _find_break_even,
    break_even_cost_multiplier,
    break_even_fee_bps,
    cost_sensitivity_sweep,
)
from src.market.history import load_dataset, snapshots_from_dataset
from scripts.run_strategy_baseline import make_series


def _flat_series(count: int = 40):
    """A dead-flat series on which no strategy should ever fire (0 trades)."""
    from src.market.models import Candle, MarketSnapshot
    out = []
    start = 1_700_000_000_000
    for i in range(count):
        closes = [100.0] * max(8, i + 1)
        candles = tuple(Candle("1m", c - 0.5, c + 1, c - 1, c, 10, start + j * 60_000)
                        for j, c in enumerate(closes))
        ts = start + (len(closes) - 1) * 60_000
        out.append(MarketSnapshot("BTCUSDT", 100.0, 99.99, 100.01, 0.0, 100, ts, ts,
                                  candles=candles).with_hash())
    return tuple(out)


def test_sweep_reports_zero_cost_floor_and_no_added_trades():
    """At multiplier 0 every scalable cost is zero, so net equals the gross edge
    minus the (fixed per-trade) spread. Raising the multiplier can only skip
    trades, never add them, so closed_trades must be non-increasing across the
    ladder."""
    cfg = BaselineConfig()
    series = make_series()
    sweep = cost_sensitivity_sweep(series, cfg)

    assert sweep["base_fee_bps"] == cfg.fee_bps
    assert sweep["closed_trades_nonincreasing"] is True

    zero = run_baseline(series, replace(cfg, fee_bps=0.0, funding_bps=0.0, slippage_bps=0.0))
    m0 = sweep["rows"][0]
    assert m0["multiplier"] == 0.0
    assert m0["fees"] == pytest.approx(0.0)
    assert m0["slippage"] == pytest.approx(0.0)
    assert m0["funding"] == pytest.approx(0.0)
    # The zero-cost floor is gross edge minus the fixed assumed spread.
    assert m0["net_pnl"] == pytest.approx(zero.net_pnl, rel=1e-9)
    assert m0["spread"] == pytest.approx(zero.spread, rel=1e-9)

    # Every row carries the cost-inclusive outcome fields for the report.
    for row in sweep["rows"]:
        for key in ("multiplier", "closed_trades", "gross_pnl", "fees", "spread",
                    "slippage", "funding", "net_pnl"):
            assert key in row


def test_break_even_absent_when_gross_edge_below_spread():
    """Negative control: the synthetic series has a negative gross edge, so even
    at zero taker/slippage/funding cost the (fixed) spread keeps net negative.
    Break-even must not exist, and the gate stays blocked."""
    cfg = BaselineConfig()
    res = break_even_fee_bps(make_series(), cfg)
    assert res["has_break_even"] is False
    assert res["selection_blocked"] is True

    # A flat series with zero trades is also a non-break-even case.
    flat = break_even_fee_bps(_flat_series(), cfg)
    assert flat["has_break_even"] is False
    assert flat["selection_blocked"] is True


def test_break_even_absent_on_real_history_even_at_zero_scalable_cost():
    """Honest real-data result: over stored public ETHUSDT 1m history the assumed
    per-trade spread dominates the gross edge, so even at zero taker/slippage/
    funding cost the zero-cost net is NEGATIVE. No break-even exists and the
    selection gate stays blocked. This is a MEASUREMENT FACT about the strategy,
    not a market verdict, and must never be flipped into a go-live claim."""
    cfg = BaselineConfig(real_funding=False)
    snapshots = snapshots_from_dataset(load_dataset(Path("data/history/ETHUSDT_1m.json")))

    res = break_even_fee_bps(snapshots, cfg)
    assert res["has_break_even"] is False
    assert res["selection_blocked"] is True
    assert res["reason"] == "NET_NEGATIVE_EVEN_AT_ZERO_COST"

    # The zero-cost floor isolates gross edge minus the assumed spread; on this
    # data it is negative (spread ~160 bps > gross edge ~78), which is exactly why
    # no break-even exists. Asserting the sign makes the test bind to the real
    # finding rather than a coincidence.
    assert res["zero_cost_net"] < 0
    assert res["zero_cost_net"] == pytest.approx(res["gross_pnl"] - res["spread"], rel=1e-6)


def test_find_break_even_interpolation():
    """Direct positive control for the interpolation MATH (real code, no engine):
    a descending zero crossing between two sweep points must be interpolated, an
    exact lower-bound crossing (zero span) must return the lower multiplier, and a
    monotonic-negative ladder must report no crossing."""
    # Descending crossing at m=0.5 (net 100 -> -100).
    rows = [{"multiplier": 0.0, "net_pnl": 100.0},
            {"multiplier": 1.0, "net_pnl": -100.0}]
    m_star, lower, upper = _find_break_even(rows)
    assert m_star == pytest.approx(0.5, rel=1e-9)
    assert lower is not None and upper is not None
    assert lower["multiplier"] == 0.0 and upper["multiplier"] == 1.0

    # Exact lower-bound crossing (span == 0): returns the lower multiplier.
    rows_eq = [{"multiplier": 0.5, "net_pnl": 0.0},
               {"multiplier": 0.5, "net_pnl": -5.0}]
    m_eq, _, _ = _find_break_even(rows_eq)
    assert m_eq == 0.5

    # Monotonic negative: no crossing.
    rows_neg = [{"multiplier": 0.0, "net_pnl": -10.0},
                {"multiplier": 1.0, "net_pnl": -20.0}]
    assert _find_break_even(rows_neg) == (None, None, None)


def test_break_even_fee_bps_happy_path_with_fake_engine():
    """Positive control for the PUBLIC break-even path: with a fake engine whose
    net declines linearly with the cost multiplier (net 50 -> -50, crossing at m=0.5)
    the function must report has_break_even=True, the interpolated multiplier, the
    implied fee (base 5 bps * 0.5 = 2.5 bps), and a verdict that is always
    selection_blocked. This exercises the verdict/implied-fee code the real-history
    test never reaches, using a fake dependency (not a fake of the SUT)."""
    cfg = BaselineConfig()  # base fee_bps = 5.0
    m_by_fee = {}

    def fake_engine(snapshots, scaled_cfg):
        m = scaled_cfg.fee_bps / cfg.fee_bps  # recover multiplier
        m_by_fee[m] = True
        net = 50.0 - 100.0 * m
        return BaselineResult(
            snapshots=len(snapshots), network_calls=0, signed_calls=0, orders=0,
            closed_trades=int(100 - 50 * m), open_positions=0,
            end_of_replay_closes=0, protection_attachments=0, reconciliation_checks=0,
            fees=0.0, spread=0.0, slippage=0.0, funding=0.0, gross_pnl=0.0,
            net_pnl=net, strategy_breakdown={}, regime_breakdown={},
            walk_forward_splits=(),
        )

    with patch("src.evaluation.cost_sensitivity.run_baseline", fake_engine):
        res = break_even_fee_bps(make_series(), cfg)

    assert res["has_break_even"] is True
    assert res["selection_blocked"] is True
    assert res["break_even_multiplier"] == pytest.approx(0.5, rel=1e-9)
    assert res["implied_break_even_fee_bps"] == pytest.approx(2.5, rel=1e-9)
    assert res["realistic_fee_bps"] == cfg.fee_bps
    assert res["verdict"] == "VIABLE_ONLY_BELOW_REALISTIC"
    # The engine was exercised across both sides of the crossing.
    assert 0.0 in m_by_fee and 1.0 in m_by_fee


def test_break_even_cost_multiplier_rejects_empty_snapshots():
    with pytest.raises(ValueError):
        break_even_cost_multiplier((), BaselineConfig())
