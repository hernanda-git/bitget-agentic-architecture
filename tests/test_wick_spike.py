"""Wick-spike data-quality check (TDD: RED first).

A candle can have perfectly valid OHLC geometry yet carry a phantom wick: a
high far above (or a low far below) the body relative to the prevailing price.
Candle.__post_init__ only enforces geometry (low <= open/close <= high), so a
candle whose high is 2x the prior close is still "valid" but is almost always a
data glitch or a forged/garbage bar. Such a wick poisons volatility-band
estimates, breakout triggers, and liquidation-price math in walk-forward replay.

This module adds:
* a measured fact ``max_wick_spike_bps`` (worst upper/lower wick vs prior close),
* a measured count ``wick_spike_bars`` (candles exceeding a configurable bound),
* a fail-closed ``wick_spike_gate`` a walk-forward caller can use to refuse a
  dataset whose worst wick is implausible.

No signed calls, no credentials, no orders. Pure offline measurement.
"""
from pathlib import Path

from src.market.models import Candle
from src.market.history import (
    HistoryDataset,
    FundingRecord,
    data_quality_report,
    wick_spike_gate,
)

ROOT = Path(__file__).resolve().parents[1]


def _mk_candle(ts, open_=100.0, high=101.0, low=99.0, close=100.0, volume=5.0):
    return Candle("1m", open_, high, low, close, volume, ts)


def _mk_dataset(candles, funding=(), fetched_at_ms=None):
    if fetched_at_ms is None:
        fetched_at_ms = max(c.source_ts_ms for c in candles)
    return HistoryDataset(
        symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="1m",
        fetched_at_ms=fetched_at_ms, candles=tuple(candles),
        funding=tuple(FundingRecord(ft, rate) for ft, rate in funding),
        assumed_half_spread_bps=0.5,
    )


def test_wick_spike_measured_and_counted():
    """A 100%-of-price upper wick is measured in bps and counted as a spike.

    Default threshold is 5000 bps (50% of price). A wick of 100% (high = 2x the
    prior close) must exceed it and be counted; a normal ~1% wick must not.
    """
    base = _mk_candle(60_000, close=100.0)  # prior close = 100
    # Phantom upper wick: high=200 vs body at 100 -> 100% wick vs prior close.
    spike = _mk_candle(120_000, open_=100.0, high=200.0, low=100.0, close=100.0)
    normal = _mk_candle(180_000, open_=100.0, high=101.0, low=99.0, close=100.0)
    report = data_quality_report(_mk_dataset([base, spike, normal]))
    # 100% of 100 -> 10000 bps, well above the 5000 bps default threshold.
    assert report.max_wick_spike_bps >= 9900.0
    assert report.max_wick_spike_bps < 10100.0
    assert report.wick_spike_bars == 1
    # The normal candle's wick is ~1% (100 bps) -> not counted as a spike.
    normal_only = data_quality_report(_mk_dataset([base, normal]))
    assert normal_only.wick_spike_bars == 0
    assert normal_only.max_wick_spike_bps < 200.0


def test_wick_spike_gate_fails_closed_on_implausible_wick():
    """The gate refuses a dataset whose worst wick is implausible (fail-closed).

    A 100%-wick dataset must fail at the 5000 bps bound but pass at a 20000 bps
    bound; a normal ~1% dataset must pass at the default bound.
    """
    base = _mk_candle(60_000, close=100.0)
    spike = _mk_candle(120_000, open_=100.0, high=200.0, low=100.0, close=100.0)
    spike_report = data_quality_report(_mk_dataset([base, spike]))
    assert wick_spike_gate(spike_report, max_wick_spike_bps=5000.0) is False
    assert wick_spike_gate(spike_report, max_wick_spike_bps=20000.0) is True

    normal = _mk_candle(120_000, open_=100.0, high=101.0, low=99.0, close=100.0)
    normal_report = data_quality_report(_mk_dataset([base, normal]))
    assert wick_spike_gate(normal_report, max_wick_spike_bps=5000.0) is True


def test_wick_spike_first_candle_uses_own_close_fallback():
    """A single spike candle with no prior close still gets measured via fallback.

    The first candle has no prior close, so the reference price falls back to its
    own close. A 100%-wick first candle must still be detected, not ignored.
    """
    spike = _mk_candle(60_000, open_=100.0, high=200.0, low=100.0, close=100.0)
    report = data_quality_report(_mk_dataset([spike]))
    assert report.max_wick_spike_bps >= 9900.0
    assert report.wick_spike_bars == 1


def test_wick_spike_gate_rejects_bad_threshold():
    """A non-finite or negative threshold is a programming error, not a pass."""
    base = _mk_candle(60_000, close=100.0)
    normal = _mk_candle(120_000, open_=100.0, high=101.0, low=99.0, close=100.0)
    report = data_quality_report(_mk_dataset([base, normal]))
    import math
    try:
        wick_spike_gate(report, max_wick_spike_bps=float("nan"))
        assert False, "expected ValueError for non-finite threshold"
    except ValueError:
        pass
    try:
        wick_spike_gate(report, max_wick_spike_bps=-1.0)
        assert False, "expected ValueError for negative threshold"
    except ValueError:
        pass
    # Sanity: finite positive threshold still works.
    assert wick_spike_gate(report, max_wick_spike_bps=5000.0) is True


def test_evaluator_cli_fails_closed_on_wick_spike(tmp_path):
    """The evaluation CLI must reject a phantom-wick dataset before any replay.

    A candle with valid OHLC geometry but a 100%-of-price wick is a data glitch/
    forged bar. The CLI's wick-spike gate must refuse it (returncode != 0), report
    the measured worst wick, and must NOT write an output file (no replay of junk).
    """
    import json
    import subprocess
    import sys

    from src.market.models import Candle
    from src.market.history import HistoryDataset, FundingRecord

    base = Candle("1m", 100.0, 101.0, 99.0, 100.0, 5.0, 60_000)
    # Valid geometry, but high = 2x the prior close -> 100% phantom upper wick.
    spike = Candle("1m", 100.0, 200.0, 100.0, 100.0, 5.0, 120_000)
    good = Candle("1m", 100.0, 101.0, 99.0, 100.0, 5.0, 180_000)
    dataset = HistoryDataset(
        symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="1m",
        fetched_at_ms=180_000, candles=(base, spike, good),
        funding=(FundingRecord(120_000, 0.0001),), assumed_half_spread_bps=0.5,
    )
    dataset_path = tmp_path / "wick.json"
    dataset_path.write_text(json.dumps(dataset.to_dict(), indent=2, sort_keys=True) + "\n")
    output_path = tmp_path / "out.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_real_history.py"),
         "--dataset", str(dataset_path), "--output", str(output_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "max_wick_spike_bps=" in (proc.stdout + proc.stderr)
    assert "wick_rejected=True" in (proc.stdout + proc.stderr)
    assert not output_path.exists()
