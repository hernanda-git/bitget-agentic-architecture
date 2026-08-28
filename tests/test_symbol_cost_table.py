"""Symbol-specific observed-spread cost table (TDD, fail-closed).

Phase 36 measured a real-venue per-symbol top-of-book spread and proved a single
global assumed spread is simultaneously too conservative on majors (BTC/ETH/SOL
~0.01-0.1 bps) and too optimistic on alts (ADA ~4.8 bps, AVAX/SUI/NEAR ~1.3-1.6
bps). This module turns that measurement into a loadable, fail-closed cost table
and a per-symbol bid/ask recalibration so the deterministic baseline replays with
the OBSERVED spread instead of the single global assumed half-spread.

Tests first (RED): the module and its helpers do not exist yet.
"""
from __future__ import annotations
import json

import pytest


def test_loader_and_helpers_exist():
    """RED anchor: the table module and every public helper must exist."""
    from src.evaluation import symbol_cost_table
    for name in ("ObservedCostTable", "load_observed_spread_table", "liquidity_tier",
                 "classify_symbols", "tier_median_spread", "recalibrate_spread",
                 "recalibrate_snapshots_by_symbol"):
        assert hasattr(symbol_cost_table, name)


def test_load_observed_spread_table_from_phase36_artifact():
    """The real committed Phase 36 calibration JSON must load into the table."""
    from pathlib import Path
    from src.evaluation.symbol_cost_table import load_observed_spread_table
    path = Path("reports/phase-36/orderbook_calibration.json")
    tbl = load_observed_spread_table(path)
    assert "BTCUSDT" in tbl.spreads_bps
    assert tbl.spreads_bps["BTCUSDT"] == pytest.approx(0.012590533807889956)
    # all 8 symbols from the artifact are present
    assert len(tbl.spreads_bps) == 8
    assert tbl.source == str(path)


def test_load_rejects_missing_file():
    from pathlib import Path
    from src.evaluation.symbol_cost_table import load_observed_spread_table
    with pytest.raises(FileNotFoundError):
        load_observed_spread_table(Path("does/not/exist.json"))


def test_load_rejects_malformed_missing_calibration_key(tmp_path):
    from src.evaluation.symbol_cost_table import load_observed_spread_table
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"symbols": ["BTCUSDT"]}))  # no "calibration" key
    with pytest.raises(ValueError):
        load_observed_spread_table(p)


def test_load_omits_symbols_without_valid_spread(tmp_path):
    """Fail-closed: a symbol with no valid observed spread is omitted, never
    presented as cheap (it must not silently fall back to a global constant)."""
    from src.evaluation.symbol_cost_table import load_observed_spread_table
    p = tmp_path / "partial.json"
    p.write_text(json.dumps({"calibration": {
        "BTCUSDT": {"n_valid": 3, "spread_bps_median": 0.01},
        "BADUSDT": {"n_valid": 0, "spread_bps_median": None},
        "NEGUSDT": {"n_valid": 3, "spread_bps_median": -0.5},
    }}))
    tbl = load_observed_spread_table(p)
    assert "BTCUSDT" in tbl.spreads_bps
    assert "BADUSDT" not in tbl.spreads_bps
    assert "NEGUSDT" not in tbl.spreads_bps


def test_spread_for_fail_closed_on_unknown():
    from src.evaluation.symbol_cost_table import ObservedCostTable
    tbl = ObservedCostTable(spreads_bps={"BTCUSDT": 0.01}, source="t")
    with pytest.raises(KeyError):
        tbl.spread_for("ETHUSDT")


def test_liquidity_tier_thresholds():
    from src.evaluation.symbol_cost_table import liquidity_tier, LiquidityTier
    assert liquidity_tier(0.05) == LiquidityTier.TIER_TIGHT
    # boundary: >= 0.1 bps is moderate (not tight)
    assert liquidity_tier(0.1) == LiquidityTier.TIER_MODERATE
    assert liquidity_tier(0.7) == LiquidityTier.TIER_MODERATE
    # boundary: >= 1.0 bps is wide
    assert liquidity_tier(1.0) == LiquidityTier.TIER_WIDE
    assert liquidity_tier(4.8) == LiquidityTier.TIER_WIDE


def test_classify_symbols_groups_and_unknown():
    from src.evaluation.symbol_cost_table import (
        ObservedCostTable, classify_symbols, LiquidityTier)
    tbl = ObservedCostTable(spreads_bps={"BTC": 0.01, "XRP": 0.7, "ADA": 4.8},
                            source="t")
    groups = classify_symbols(tbl, ["BTC", "XRP", "ADA", "UNKNOWN"])
    assert set(groups[LiquidityTier.TIER_TIGHT]) == {"BTC"}
    assert set(groups[LiquidityTier.TIER_MODERATE]) == {"XRP"}
    assert set(groups[LiquidityTier.TIER_WIDE]) == {"ADA"}
    assert set(groups[LiquidityTier.UNKNOWN]) == {"UNKNOWN"}


def test_tier_median_spread():
    from src.evaluation.symbol_cost_table import ObservedCostTable, tier_median_spread
    tbl = ObservedCostTable(spreads_bps={"BTC": 0.01, "ETH": 0.04, "SOL": 0.095},
                            source="t")
    assert tier_median_spread(tbl, ["BTC", "ETH", "SOL"]) == pytest.approx(0.04)
    with pytest.raises(ValueError):
        tier_median_spread(tbl, ["UNKNOWN"])  # no observed spread


def _mk_snap(symbol="BTCUSDT", mark=100.0):
    from src.market.models import Candle, MarketSnapshot
    candle = Candle("1m", 99.0, 101.0, 98.0, 100.0, 10, 1_700_000_000_000)
    return MarketSnapshot(symbol, mark, mark - 0.01, mark + 0.01, 0.0, 100,
                          1_700_000_000_000, 1_700_000_000_000,
                          candles=(candle,)).with_hash()


def test_recalibrate_spread_changes_bid_ask_to_observed():
    from src.evaluation.symbol_cost_table import recalibrate_spread
    snap = _mk_snap()
    rec = recalibrate_spread(snap, 4.0)  # 4 bps full spread
    assert rec.spread_bps == pytest.approx(4.0)
    assert rec.bid < rec.ask
    assert rec.mark_price == pytest.approx(100.0)
    # the mark is preserved so the realized round-trip spread equals the observed one
    assert (rec.ask - rec.bid) == pytest.approx(100.0 * 4.0 / 10_000)


def test_recalibrate_spread_rejects_nonpositive():
    from src.evaluation.symbol_cost_table import recalibrate_spread
    snap = _mk_snap()
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            recalibrate_spread(snap, bad)


def test_recalibrate_snapshots_by_symbol_fail_closed_on_missing():
    from src.evaluation.symbol_cost_table import (
        ObservedCostTable, recalibrate_snapshots_by_symbol)
    tbl = ObservedCostTable(spreads_bps={"BTCUSDT": 0.01}, source="t")
    snap = _mk_snap("ETHUSDT")
    with pytest.raises(KeyError):
        recalibrate_snapshots_by_symbol((snap,), tbl)


def test_recalibrate_snapshots_by_symbol_applies_per_symbol():
    from src.evaluation.symbol_cost_table import (
        ObservedCostTable, recalibrate_snapshots_by_symbol)
    tbl = ObservedCostTable(spreads_bps={"BTCUSDT": 0.01, "ETHUSDT": 0.04}, source="t")
    out = recalibrate_snapshots_by_symbol((_mk_snap("BTCUSDT"), _mk_snap("ETHUSDT")), tbl)
    assert out[0].spread_bps == pytest.approx(0.01)
    assert out[1].spread_bps == pytest.approx(0.04)
