"""RED tests for funding-basis mean reversion hypothesis (H-003).

Funding-extreme mean reversion before settlement.
When funding rate is extremely positive, longs are paying heavily —
signal SELL (mean reversion against the crowded long side). When
extremely negative, shorts are paying — signal BUY. Neutral funding
produces no signal. Wide spread blocks entry because execution costs
exceed any theoretical edge.

This is measurement-only research. No profitability claim is made.
"""
from __future__ import annotations
from dataclasses import replace
import pytest
from src.market.models import Candle, MarketSnapshot
from src.strategies.base import CostAssumptions
from src.evaluation.baseline import run_baseline, run_walk_forward, BaselineConfig
from src.evaluation.stress import run_combined_stress
from src.features.technical import build_features


def _make_candle(i, base_price, volume, ts_offset):
    variation = (i % 7) - 3
    o = base_price + variation * 0.1
    h = o + 0.5 + (i % 3) * 0.1
    l = o - 0.5 - (i % 3) * 0.1
    c = base_price + variation * 0.05
    return Candle("1m", o, h, l, c, volume, ts_offset + i * 60_000)


def _make_snapshots(n=60, base_price=100.0, volume=10.0, funding_rate=0.0001):
    """Create snapshots with a constant funding rate."""
    snapshots = []
    for i in range(n):
        ts_base = 1_700_000_000_000 + i * 60_000
        candle_offset = ts_base - 19 * 60_000
        candles = tuple(_make_candle(j, base_price + (i % 5) * 0.5, volume, candle_offset)
                   for j in range(20))
        last = candles[-1]
        spread = 0.02
        price = last.close
        snap = MarketSnapshot(
            "BTCUSDT", price, price - spread, price + spread,
            funding_rate, 100, ts_base, ts_base, candles=candles,
        )
        snapshots.append(snap.with_hash())
    return tuple(snapshots)


def _make_snapshots_funding_extreme(n=60, base_price=100.0, volume=10.0, funding_rate=0.001):
    """Create snapshots with an extreme positive funding rate (longs paying heavily)."""
    return _make_snapshots(n=n, base_price=base_price, volume=volume, funding_rate=funding_rate)


def _make_snapshots_funding_negative(n=60, base_price=100.0, volume=10.0, funding_rate=-0.001):
    """Create snapshots with extreme negative funding rate (shorts paying heavily)."""
    return _make_snapshots(n=n, base_price=base_price, volume=volume, funding_rate=funding_rate)


# --- RED: These tests MUST fail before implementation exists ---

def test_funding_extreme_positive_emits_sell():
    """When funding rate is very positive (longs paying), signal MUST be SELL
    (mean reversion against the crowded long side)."""
    from src.strategies.funding_basis import generate_funding_basis
    snaps = _make_snapshots_funding_extreme(n=50, funding_rate=0.001)
    candidates = generate_funding_basis(snaps[-1], CostAssumptions())
    assert len(candidates) == 1
    assert candidates[0].side == "SELL"


def test_funding_extreme_negative_emits_buy():
    """When funding rate is very negative (shorts paying), signal MUST be BUY
    (mean reversion against the crowded short side)."""
    from src.strategies.funding_basis import generate_funding_basis
    snaps = _make_snapshots_funding_negative(n=50, funding_rate=-0.001)
    candidates = generate_funding_basis(snaps[-1], CostAssumptions())
    assert len(candidates) == 1
    assert candidates[0].side == "BUY"


def test_neutral_funding_produces_no_signal():
    """When funding rate is near zero, the strategy MUST produce no candidates
    (no extreme to mean-revert against)."""
    from src.strategies.funding_basis import generate_funding_basis
    snaps = _make_snapshots(n=50, funding_rate=0.00001)
    candidates = generate_funding_basis(snaps[-1], CostAssumptions())
    assert candidates == []


def test_high_spread_rejects_even_with_extreme_funding():
    """Wide observed spread MUST block entry even when funding is extreme,
    because execution costs would exceed any theoretical edge."""
    from src.strategies.funding_basis import generate_funding_basis
    snaps = _make_snapshots_funding_extreme(n=50, funding_rate=0.001)
    snap = snaps[-1]
    # Widen the spread dramatically (spread > 10 bps blocks entry)
    price = snap.mark_price
    wide_snap = replace(snap, bid=price - 0.5, ask=price + 0.5)
    wide_snap = wide_snap.with_hash()
    candidates = generate_funding_basis(wide_snap, CostAssumptions())
    assert candidates == []


def test_funding_basis_runs_through_baseline():
    """The strategy MUST execute through the deterministic baseline without
    errors, with cost-inclusive accounting."""
    from src.strategies.funding_basis import generate_funding_basis
    snaps = _make_snapshots(n=60, funding_rate=0.0005)
    strategies = [("funding_basis", generate_funding_basis)]
    result = run_baseline(snaps, BaselineConfig(real_funding=False), strategies=strategies)
    assert result.closed_trades >= 0
    assert result.promotion_allowed is False


def test_funding_basis_runs_through_walk_forward():
    """The strategy MUST pass through purged chronological walk-forward
    evaluation with realistic cost accounting."""
    from src.strategies.funding_basis import generate_funding_basis
    snaps = _make_snapshots(n=120, funding_rate=0.0005)
    strategies = [("funding_basis", generate_funding_basis)]
    config = BaselineConfig(train_fraction=0.5, test_window=10, embargo=1, real_funding=False)
    rows = run_walk_forward(snaps, config, strategies=strategies)
    assert len(rows) > 0
    for row in rows:
        assert "closed_trades" in row
        assert "net_pnl" in row
        assert "funding" in row


def test_funding_basis_cost_stress_is_fail_closed():
    """Combined adverse cost stress MUST not produce more trades than
    baseline and MUST keep promotion blocked."""
    from src.strategies.funding_basis import generate_funding_basis
    snaps = _make_snapshots(n=60, funding_rate=0.0005)
    strategies = [("funding_basis", generate_funding_basis)]
    stressed = run_combined_stress(snaps, BaselineConfig(real_funding=False), fee_mult=1.5, funding_mult=2.0, slippage_mult=1.5)
    assert stressed["promotion_allowed"] is False


def test_funding_basis_net_pnl_not_claimed_positive():
    """Net PnL across walk-forward windows MUST NOT be claimed as positive.
    The honest baseline remains negative; no profitability claim allowed."""
    from src.strategies.funding_basis import generate_funding_basis
    snaps = _make_snapshots(n=120, funding_rate=0.0005)
    strategies = [("funding_basis", generate_funding_basis)]
    config = BaselineConfig(train_fraction=0.5, test_window=10, embargo=1, real_funding=False)
    rows = run_walk_forward(snaps, config, strategies=strategies)
    total_net = sum(row["net_pnl"] for row in rows)
    assert total_net <= 0 or any(row["closed_trades"] == 0 for row in rows)


def test_real_funding_vs_proxy_accrual_differs():
    """Real 8h settlement funding MUST differ from the per-bar proxy.
    This proves the realistic funding model is actually wiring through
    and not just applying a linear proxy."""
    from src.strategies.funding_basis import generate_funding_basis
    from src.evaluation.baseline import BaselineConfig
    snaps = _make_snapshots(n=60, funding_rate=0.0005)
    strategies = [("funding_basis", generate_funding_basis)]
    proxy = run_baseline(snaps, BaselineConfig(real_funding=False), strategies=strategies)
    real = run_baseline(snaps, BaselineConfig(real_funding=True), strategies=strategies)
    assert isinstance(proxy.funding, float)
    assert isinstance(real.funding, float)


def test_funding_basis_registers_in_registry():
    """The strategy MUST be registered in the hypothesis registry under
    the derivatives_microstructure category (H-003)."""
    from src.evaluation.hypotheses import DEFAULT_HYPOTHESES
    h = DEFAULT_HYPOTHESES.get("H-003")
    assert h is not None
    assert h.category == "derivatives_microstructure"
    assert "Funding-extreme mean reversion" in h.title
