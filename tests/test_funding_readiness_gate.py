"""Funding-coverage fail-closed gate for real-history evaluation (TDD: RED first).

When the evaluator models real funding (``real_funding=True``) it must not
silently fall back to a flat per-bar funding proxy when the dataset has no
funding settlements in range. Missing funding coverage means the cost model is
unmodeled, not cheap. The gate must fail closed and say so.

No signed calls, no credentials, no orders. Pure offline measurement.
"""
from pathlib import Path

import pytest

from src.market.models import Candle
from src.market.history import HistoryDataset, FundingRecord, data_quality_report, real_funding_readiness

ROOT = Path(__file__).resolve().parents[1]


def _mk_candle(ts, close=100.0):
    return Candle("5m", close * 0.999, close * 1.001, close * 0.998, close, 5.0, ts)


def _mk_dataset(candles, funding=(), fetched_at_ms=None):
    if fetched_at_ms is None:
        fetched_at_ms = max(c.source_ts_ms for c in candles)
    return HistoryDataset(
        symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="5m",
        fetched_at_ms=fetched_at_ms, candles=tuple(candles),
        funding=tuple(FundingRecord(ft, rate) for ft, rate in funding),
        assumed_half_spread_bps=0.5,
    )


def test_real_funding_readiness_fails_when_no_funding_records_in_range():
    """A dataset spanning funding settlements but with zero funding records is not ready."""
    # 600 5m bars ~= 50h ~= 6 eight-hour funding settlements.
    candles = [_mk_candle(5 * 60_000 * i) for i in range(1, 601)]
    dataset = _mk_dataset(candles, funding=())
    report = data_quality_report(dataset)
    readiness = real_funding_readiness(dataset, report)
    assert readiness.ok is False
    assert "funding" in readiness.reason.lower()
    assert readiness.funding_records_in_range == 0


def test_real_funding_readiness_ok_with_adequate_coverage():
    """Adequate in-range funding settlements make the dataset ready for real funding."""
    candles = [_mk_candle(5 * 60_000 * i) for i in range(1, 601)]
    funding = [(8 * 3_600_000 * k, 0.0001) for k in range(1, 7)]
    dataset = _mk_dataset(candles, funding=funding)
    report = data_quality_report(dataset)
    readiness = real_funding_readiness(dataset, report)
    assert readiness.ok is True
    assert readiness.funding_records_in_range >= 1
    assert readiness.reason == ""


def test_real_funding_readiness_fails_on_excessive_missing_fraction():
    """Heavy gaps in funding coverage (most settlements missing) must fail closed."""
    candles = [_mk_candle(5 * 60_000 * i) for i in range(1, 601)]
    # One settlement present, but ~5 settlements expected -> high missing fraction.
    funding = [(8 * 3_600_000, 0.0001)]
    dataset = _mk_dataset(candles, funding=funding)
    report = data_quality_report(dataset)
    readiness = real_funding_readiness(dataset, report, max_funding_missing_fraction=0.5)
    assert readiness.ok is False
    assert readiness.funding_missing > 0


def test_evaluator_fails_closed_without_funding_coverage(tmp_path):
    """evaluate_real_history must refuse real funding when coverage is absent."""
    import json
    import subprocess
    import sys

    candles = [_mk_candle(5 * 60_000 * i) for i in range(1, 601)]
    dataset = _mk_dataset(candles, funding=())
    dataset_path = tmp_path / "nofunding.json"
    dataset_path.write_text(json.dumps(dataset.to_dict(), indent=2, sort_keys=True) + "\n")
    output_path = tmp_path / "out.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_real_history.py"),
         "--dataset", str(dataset_path), "--output", str(output_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "FUNDING_COVERAGE" in (proc.stdout + proc.stderr)
    assert not output_path.exists()
