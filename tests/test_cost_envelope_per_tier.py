"""Per-liquidity-tier cost-stress envelope (TDD, measurement only).

Phase 36 showed the cost model must stop using one global assumed spread. This
suite covers ``cost_envelope_per_tier``: it recalibrates each symbol's spread to
the observed real-venue value, runs the existing cost-stress envelope per symbol,
and aggregates the envelope per liquidity tier. It is measurement only and always
keeps the Phase 6 promotion gate blocked (no winner/promoted/selected/positive-edge
key is ever emitted).

Tests first (RED): the function does not exist yet.
"""
from __future__ import annotations
from unittest.mock import patch

import pytest

from src.evaluation.symbol_cost_table import ObservedCostTable, LiquidityTier


def _mk_snap(symbol):
    from src.market.models import Candle, MarketSnapshot
    candle = Candle("1m", 99.0, 101.0, 98.0, 100.0, 10, 1_700_000_000_000)
    return MarketSnapshot(symbol, 100.0, 99.99, 100.01, 0.0, 100,
                          1_700_000_000_000, 1_700_000_000_000,
                          candles=(candle,)).with_hash()


def _fake_envelope(net_for_symbol):
    def _env(snapshots, config, *, fee_mults=(1.0,), funding_mults=(1.0,),
             slippage_mults=(1.0,)):
        symbol = snapshots[0].symbol
        nets = net_for_symbol[symbol]
        cells = [{"net_pnl": n, "fee_mult": 1.0, "funding_mult": 1.0,
                  "slippage_mult": 1.0, "gross_pnl": 0.0, "fees": 0.0,
                  "spread": 0.0, "slippage": 0.0, "funding": 0.0,
                  "closed_trades": 1, "drawdown": 0.0} for n in nets]
        return {"cells": cells, "selection_blocked": True, "promotion_blocked": True}
    return _env


def test_cost_envelope_per_tier_groups_and_aggregates():
    from src.evaluation.cost_sensitivity import cost_envelope_per_tier
    tbl = ObservedCostTable(
        spreads_bps={"BTCUSDT": 0.01, "ETHUSDT": 0.04, "XRPUSDT": 0.7,
                     "ADAUSDT": 4.8, "MISSXUSDT": 1.0},
        source="t")
    sym_snaps = [("BTCUSDT", (_mk_snap("BTCUSDT"),)), ("ETHUSDT", (_mk_snap("ETHUSDT"),)),
                 ("XRPUSDT", (_mk_snap("XRPUSDT"),)), ("ADAUSDT", (_mk_snap("ADAUSDT"),)),
                 ("MISSXUSDT", (_mk_snap("MISSXUSDT"),)),
                 ("MISSINGUSDT", (_mk_snap("MISSINGUSDT"),))]
    net_for_symbol = {"BTCUSDT": [-10.0, -20.0], "ETHUSDT": [-5.0, -15.0],
                      "XRPUSDT": [2.0, -3.0], "ADAUSDT": [-50.0, -60.0],
                      "MISSXUSDT": [-1.0, -2.0]}
    with patch("src.evaluation.cost_sensitivity.cost_envelope_sweep",
               _fake_envelope(net_for_symbol)):
        res = cost_envelope_per_tier(sym_snaps, tbl)
    assert res["selection_blocked"] is True
    assert res["promotion_blocked"] is True
    tiers = res["tiers"]
    # tight (<0.1): BTC, ETH ; moderate (0.1-1.0): XRP ; wide (>=1.0): ADA, MISSX
    assert set(tiers["TIER_TIGHT"]["symbols"]) == {"BTCUSDT", "ETHUSDT"}
    assert set(tiers["TIER_MODERATE"]["symbols"]) == {"XRPUSDT"}
    assert set(tiers["TIER_WIDE"]["symbols"]) == {"ADAUSDT", "MISSXUSDT"}
    assert res["unknown_symbols"] == ["MISSINGUSDT"]
    # aggregation math is correct across each tier's cells
    assert tiers["TIER_TIGHT"]["min_net"] == pytest.approx(-20.0)
    assert tiers["TIER_TIGHT"]["max_net"] == pytest.approx(-5.0)
    assert tiers["TIER_MODERATE"]["any_profitable"] is True   # XRP has +2.0
    assert tiers["TIER_WIDE"]["any_profitable"] is False
    # fail-closed: no promotion vocabulary leaks in
    for forbidden in ("winner", "promoted", "selected", "go_live", "positive_edge"):
        assert forbidden not in res


def test_cost_envelope_per_tier_recalibrates_observed_spread():
    """The per-symbol envelope must be called on snapshots whose bid/ask carry
    the OBSERVED spread, not the global assumed half-spread."""
    from src.evaluation.cost_sensitivity import cost_envelope_per_tier
    tbl = ObservedCostTable(spreads_bps={"BTCUSDT": 0.0126}, source="t")
    seen = {}

    def _capture(snapshots, config, *, fee_mults=(1.0,), funding_mults=(1.0,),
                 slippage_mults=(1.0,)):
        seen["spread_bps"] = snapshots[0].spread_bps
        cells = [{"net_pnl": -1.0, "fee_mult": 1.0, "funding_mult": 1.0,
                  "slippage_mult": 1.0, "gross_pnl": 0.0, "fees": 0.0,
                  "spread": 0.0, "slippage": 0.0, "funding": 0.0,
                  "closed_trades": 1, "drawdown": 0.0}]
        return {"cells": cells, "selection_blocked": True, "promotion_blocked": True}

    with patch("src.evaluation.cost_sensitivity.cost_envelope_sweep", _capture):
        cost_envelope_per_tier([("BTCUSDT", (_mk_snap("BTCUSDT"),))], tbl,
                               fee_mults=(1.0,), funding_mults=(1.0,), slippage_mults=(1.0,))
    assert seen["spread_bps"] == pytest.approx(0.0126)


def test_cost_envelope_per_tier_real_history_blocked():
    """Honest real-shaped check over already-local public history (no egress):
    recalibrate BTCUSDT + ADAUSDT to their observed spreads and confirm the
    per-tier envelope stays fully blocked."""
    from pathlib import Path
    from src.market.history import load_dataset, snapshots_from_dataset
    from src.evaluation.cost_sensitivity import cost_envelope_per_tier
    from src.evaluation.baseline import BaselineConfig
    tbl = ObservedCostTable(
        spreads_bps={"BTCUSDT": 0.012590533807889956, "ADAUSDT": 4.797313504436987},
        source="phase-36")
    sym_snaps = []
    for sym, path in (("BTCUSDT", "data/history/BTCUSDT_1m.json"),
                      ("ADAUSDT", "data/history/ADAUSDT_1m.json")):
        snaps = snapshots_from_dataset(load_dataset(Path(path)))[:300]
        sym_snaps.append((sym, snaps))
    res = cost_envelope_per_tier(sym_snaps, tbl, BaselineConfig(real_funding=False),
                                 fee_mults=(1.0, 2.0), funding_mults=(1.0, 2.0),
                                 slippage_mults=(1.0, 2.0))
    assert res["selection_blocked"] is True
    assert res["promotion_blocked"] is True
    # TIER_TIGHT = BTC, TIER_WIDE = ADA; both blocked
    assert "TIER_TIGHT" in res["tiers"] and "TIER_WIDE" in res["tiers"]
    assert res["tiers"]["TIER_TIGHT"]["all_blocked"] is True
    assert res["tiers"]["TIER_WIDE"]["all_blocked"] is True
