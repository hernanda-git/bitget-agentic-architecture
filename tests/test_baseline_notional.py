"""R1: baseline must size quantity from a notional cap, not a hardcoded 1.0 contract.

RED first: these must fail against the current `quantity=1.0` baseline that
ignores ``max_position_notional_usd`` and never reports the actual per-position
notional it traded.

The deterministic baseline is negative and Phase 6 selection stays blocked; this
module only changes HOW the baseline sizes a position (honest small-notional
cost/reward scaling), never any promotion gate.
"""
from __future__ import annotations

import pytest

from src.evaluation.baseline import BaselineConfig, effective_quantity, run_baseline
from scripts.run_strategy_baseline import make_series


def test_effective_quantity_derived_from_notional_cap():
    cfg = BaselineConfig(max_position_notional_usd=25.0, quantity=1.0)
    # At a $60k mark the notional cap implies ~0.0004167 contracts, far below the
    # default 1.0 contract (which would be a ~$60k notional position).
    q = effective_quantity(cfg, 60000.0)
    assert q == pytest.approx(25.0 / 60000.0, rel=1e-9)
    assert q < 1.0
    # At a ~$100 mark the cap implies ~0.25 contracts.
    assert effective_quantity(cfg, 100.0) == pytest.approx(0.25, rel=1e-9)


def test_effective_quantity_respects_hard_quantity_cap():
    # When the notional-implied quantity exceeds the hard contract cap, the cap wins.
    cfg = BaselineConfig(max_position_notional_usd=200_000.0, quantity=1.0)
    assert effective_quantity(cfg, 60000.0) == pytest.approx(1.0, rel=1e-9)


def test_effective_quantity_disabled_when_notional_zero_or_bad_mark():
    # A zero/disabled notional cap means "use the configured quantity" (no sizing).
    cfg = BaselineConfig(max_position_notional_usd=0.0, quantity=1.0)
    assert effective_quantity(cfg, 60000.0) == pytest.approx(1.0, rel=1e-9)
    # A non-positive mark must never produce a division blow-up; fall back to quantity.
    assert effective_quantity(cfg, 0.0) == pytest.approx(1.0, rel=1e-9)


def test_run_baseline_sizes_to_notional_and_reports_small_fees():
    series = make_series()
    # Notional cap of $25 with ~$100 marks => ~0.25 contracts per position.
    capped = BaselineConfig(max_position_notional_usd=25.0, quantity=1.0)
    res = run_baseline(series, capped)
    assert res.closed_trades >= 1
    # The reported per-position notional must reflect the cap (~$25), not the
    # ~$100 notional implied by a hardcoded 1.0 contract at these marks.
    assert 15.0 <= res.position_notional_usd <= 35.0
    # Fees must scale with the tiny notional, not the full 1.0-contract notional.
    full = BaselineConfig(max_position_notional_usd=1_000_000.0, quantity=1.0)
    res_full = run_baseline(series, full)
    # The full run uses the full 1.0 contract; its fees are far larger.
    assert res.fees < res_full.fees / 2
    assert res_full.position_notional_usd > res.position_notional_usd * 2
