"""Cost-coverage entry viability gate for the deterministic baseline evaluation.

A candidate may only enter when its expected move covers a configured multiple
of its expected round-trip cost. Default coverage 1.0 preserves historical
behavior (candidates already require move > cost); higher coverage skips
marginal entries whose edge cannot plausibly pay fees + spread + slippage +
funding. Skipped entries are counted and reported, never silently dropped.
"""
from dataclasses import replace

import pytest

from src.evaluation.baseline import (
    BaselineConfig,
    run_baseline,
    run_coverage_variants,
)
from src.market.models import Candle, MarketSnapshot
from src.strategies.base import CostAssumptions
from src.strategies.trend_continuation import generate_trend_continuation
from scripts.run_strategy_baseline import make_series


def candles(closes, start=1_700_000_000_000):
    return tuple(Candle("1m", c - 0.5, c + 1, c - 1, c, 10, start + i * 60_000) for i, c in enumerate(closes))


def snapshot(closes, *, funding=0.0001, spread=0.02):
    cs = candles(closes)
    mark = closes[-1]
    ts = cs[-1].source_ts_ms
    return MarketSnapshot("BTCUSDT", mark, mark - spread / 2, mark + spread / 2, funding, 100,
                          ts, cs[-1].source_ts_ms, candles=cs, snapshot_hash="").with_hash()


def marginal_series():
    """Single snapshot where only trend_continuation fires with 1 < coverage < 2.

    momentum = 101.0 - 100.6 = 0.4 -> expected_move = 0.2.
    expected_cost ~ 101.01 * ~16bps ~ 0.16, so coverage ~ 1.24.
    """
    return (snapshot([100, 100.2, 100.4, 100.6, 100.8, 101.0]),)


def test_fixture_emits_single_marginal_trend_candidate():
    """Precondition guard: the fixture really produces one marginal candidate."""
    s = marginal_series()[0]
    costs = CostAssumptions(fee_bps=5, funding_bps=2, slippage_bps=2)
    candidates = generate_trend_continuation(s, costs)
    assert len(candidates) == 1
    coverage = candidates[0].expected_move / candidates[0].expected_cost
    assert 1.0 < coverage < 2.0


def test_default_coverage_preserves_historical_behavior():
    series = make_series()
    default_result = run_baseline(series)
    explicit_result = run_baseline(series, replace(BaselineConfig(), min_edge_coverage=1.0))
    assert default_result == explicit_result


def test_marginal_candidate_trades_by_default_and_is_skipped_at_coverage_two():
    series = marginal_series()
    cfg = BaselineConfig(quantity=1.0, fee_bps=5, funding_bps=2, slippage_bps=2)

    permissive = run_baseline(series, cfg)
    assert permissive.strategy_breakdown["trend_continuation"]["closed_trades"] == 1
    assert permissive.orders == 2  # entry + end-of-replay flatten
    assert permissive.cost_gate_skipped == 0

    strict = run_baseline(series, replace(cfg, min_edge_coverage=2.0))
    assert strict.orders == 0
    assert strict.closed_trades == 0
    assert strict.strategy_breakdown["trend_continuation"]["closed_trades"] == 0
    assert strict.cost_gate_skipped == 1


def test_min_edge_coverage_below_one_or_non_finite_fails_closed():
    series = make_series()
    with pytest.raises(ValueError):
        run_baseline(series, replace(BaselineConfig(), min_edge_coverage=0.5))
    with pytest.raises(ValueError):
        run_baseline(series, replace(BaselineConfig(), min_edge_coverage=float("nan")))


def test_run_coverage_variants_reports_each_variant_against_the_plain_baseline():
    series = make_series()
    config = BaselineConfig(quantity=1.0, fee_bps=5, funding_bps=2, slippage_bps=2)
    rows = run_coverage_variants(series, config, coverages=(1.0, 2.0, 3.0))
    assert [row["min_edge_coverage"] for row in rows] == [1.0, 2.0, 3.0]
    plain = run_baseline(series, config)
    for row in rows:
        assert set(row) >= {"min_edge_coverage", "orders", "closed_trades", "gross_pnl",
                            "fees", "net_pnl", "cost_gate_skipped"}
        assert row["cost_gate_skipped"] >= 0
        assert row["net_pnl"] == pytest.approx(
            row["gross_pnl"] - row["fees"]
            - sum(row[k] for k in ("spread", "slippage", "funding") if k in row))
    assert rows[0]["orders"] == plain.orders
    assert rows[0]["closed_trades"] == plain.closed_trades
    assert rows[0]["net_pnl"] == pytest.approx(plain.net_pnl)
    # Higher coverage can only remove trades, never add them.
    assert all(row["orders"] <= plain.orders for row in rows)
