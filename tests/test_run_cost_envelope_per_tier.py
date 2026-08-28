"""Runner for the per-liquidity-tier cost-stress envelope (TDD, offline).

Phase 36 measured a real-venue per-symbol spread and showed one global assumed
half-spread is wrong. Phase 37 turned that into ``symbol_cost_table`` +
``cost_envelope_per_tier`` (unit-tested + mutation-verified). This suite covers
the offline runner ``scripts/run_cost_envelope_per_tier.py`` that replays the
existing public historical corpus through the per-tier envelope using the
OBSERVED spread, producing committed, reproducible evidence. It is network-free
(reads ``data/history/*.json`` + the committed Phase 36 table) and always keeps
the Phase 6 promotion gate blocked.

Tests first (RED): the runner module and ``build_per_tier_report`` do not exist.
"""
from __future__ import annotations
from pathlib import Path

import json


def _write_dataset(path: Path, symbol: str, marks):
    from src.market.history import HistoryDataset
    from src.market.models import Candle

    candles = []
    ts = 1_700_000_000_000
    for i, m in enumerate(marks):
        candles.append(Candle("1m", m * 0.999, m * 1.001, m * 0.998, m, 10.0, ts + i * 60_000))
    ds = HistoryDataset(symbol=symbol, product_type="SUSDT-FUTURES", granularity="1m",
                        fetched_at_ms=ts, candles=tuple(candles), funding=(),
                        assumed_half_spread_bps=1.0)
    path.write_text(json.dumps(ds.to_dict()))


def test_runner_module_exists():
    """RED anchor: the runner module and entrypoint must exist."""
    import scripts.run_cost_envelope_per_tier as m
    assert hasattr(m, "build_per_tier_report")
    assert hasattr(m, "main")


def test_build_per_tier_report_over_synthetic(tmp_path):
    from scripts.run_cost_envelope_per_tier import build_per_tier_report
    from src.evaluation.symbol_cost_table import load_observed_spread_table

    hist = tmp_path / "hist"
    hist.mkdir()
    # BTCUSDT (tight) + ADAUSDT (wide) are in the Phase 36 table; DOGEUSDT is not.
    _write_dataset(hist / "BTCUSDT_1m.json", "BTCUSDT", [100.0] * 20)
    _write_dataset(hist / "ADAUSDT_1m.json", "ADAUSDT", [0.5] * 20)
    _write_dataset(hist / "DOGEUSDT_1m.json", "DOGEUSDT", [0.1] * 20)

    table = load_observed_spread_table(Path("reports/phase-36/orderbook_calibration.json"))
    assert "BTCUSDT" in table.spreads_bps and "ADAUSDT" in table.spreads_bps

    res = build_per_tier_report(hist, "reports/phase-36/orderbook_calibration.json", limit=20)

    # never promotes
    assert res["selection_blocked"] is True
    assert res["promotion_blocked"] is True
    # tier grouping reflects the OBSERVED spread, not a global assumption
    assert set(res["tiers"]["TIER_TIGHT"]["symbols"]) == {"BTCUSDT"}
    assert set(res["tiers"]["TIER_WIDE"]["symbols"]) == {"ADAUSDT"}
    # symbols absent from the observed-spread table are excluded (never cheap)
    assert "DOGEUSDT" in res["unknown_symbols"]
    # no promotion vocabulary leaks into the report
    for forbidden in ("winner", "promoted", "selected", "go_live", "positive_edge"):
        assert forbidden not in res
