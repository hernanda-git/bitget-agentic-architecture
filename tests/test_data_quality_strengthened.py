"""Strengthened data-quality checks for historical datasets (TDD: RED first).

These tests encode new data-quality guarantees that the existing
``DataQualityReport`` does not yet provide:

* price integrity: non-finite, non-positive, high<low, close/ open outside range
* staleness: last candle age vs fetch time (configurable freshness gate)
* single-bar outliers: largest abs close-to-close return in basis points
* funding anomalies: non-finite or extreme funding rates

No signed calls, no credentials, no orders. Pure offline measurement.
"""
from pathlib import Path

import pytest

from src.market.models import Candle
from src.market.history import HistoryDataset, FundingRecord, data_quality_report, expected_interval_ms

ROOT = Path(__file__).resolve().parents[1]


def _mk_candle(ts, close=100.0, open_=99.5, high=101.0, low=99.0, volume=5.0):
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


def test_data_quality_flags_bad_prices_and_fails_structural_ok():
    """Non-finite prices survive Candle construction but are not valid market data.

    ``Candle.__post_init__`` rejects negative, zero, and impossible geometry
    (high<low, close outside range) via comparison, but ``nan``/``inf`` make
    every comparison ``False`` and therefore slip through. The data-quality
    gate must still catch them.
    """
    good = _mk_candle(60_000)
    nan_close = Candle("1m", 100.0, 101.0, 99.0, float("nan"), 5.0, 120_000)  # nan close
    inf_high = Candle("1m", 100.0, float("inf"), 99.0, 100.0, 5.0, 180_000)   # inf high
    dataset = _mk_dataset([good, nan_close, inf_high])
    report = data_quality_report(dataset)
    assert report.bad_prices == 2
    assert report.price_integrity_ok is False
    # Structural `ok` must now also reject price-integrity failures.
    assert report.ok is False


def test_data_quality_flags_non_finite_prices():
    """NaN/inf slip past Candle construction but are not valid market data."""
    nan_close = Candle("1m", 100.0, 101.0, 99.0, float("nan"), 5.0, 60_000)
    inf_high = Candle("1m", 100.0, float("inf"), 99.0, 100.0, 5.0, 120_000)
    dataset = _mk_dataset([nan_close, inf_high])
    report = data_quality_report(dataset)
    assert report.bad_prices == 2
    assert report.price_integrity_ok is False
    assert report.ok is False


def test_data_quality_reports_data_age_and_freshness_gate():
    """Staleness is measured and a configurable freshness gate can reject it."""
    candles = [_mk_candle(60_000 * i) for i in range(1, 11)]
    # Fetched 1 hour after the final candle: clearly stale for 1m data.
    dataset = _mk_dataset(candles, fetched_at_ms=60_000 * 10 + 3_600_000)
    report = data_quality_report(dataset, max_data_age_ms=5 * 60_000)
    assert report.data_age_ms == 3_600_000
    assert report.freshness_ok is False
    # Without a configured gate, staleness is reported but not a hard failure.
    loose = data_quality_report(dataset)
    assert loose.data_age_ms == 3_600_000
    assert loose.max_data_age_ms is None
    assert loose.freshness_ok is True
    assert loose.ok is True


def test_data_quality_reports_max_single_bar_return_outlier():
    """A flash candle produces a large close-to-close return in bps."""
    candles = [
        _mk_candle(60_000, close=100.0),
        _mk_candle(120_000, close=100.0),
        # ~50% single-bar move vs the prior close (valid geometry, extreme move).
        _mk_candle(180_000, close=150.0, open_=150.0, high=150.0, low=150.0),
        _mk_candle(240_000, close=150.0, open_=150.0, high=150.0, low=150.0),
    ]
    report = data_quality_report(_mk_dataset(candles))
    # 50% of 100 -> 5000 bps. Small normal moves contribute far less.
    assert report.max_single_bar_return_bps >= 4900.0
    assert report.max_single_bar_return_bps < 5100.0


def test_data_quality_flags_funding_anomalies():
    """Extreme or non-finite funding rates are flagged, sane ones are not."""
    candles = [_mk_candle(60_000 * i) for i in range(1, 11)]
    funding = [
        (120_000, 0.0001),       # sane
        (600_000, 0.5),          # absurd 50% per settlement
        (1_200_000, float("nan")),  # non-finite
    ]
    report = data_quality_report(_mk_dataset(candles, funding=funding))
    assert report.funding_anomalies == 2
    # Sane-only dataset reports zero anomalies.
    sane = data_quality_report(_mk_dataset(candles, funding=[(120_000, 0.0001)]))
    assert sane.funding_anomalies == 0


def test_evaluator_cli_fails_closed_on_bad_prices(tmp_path):
    """The evaluation gate must reject impossible OHLC before any replay."""
    import json
    import subprocess
    import sys

    # Non-finite high survives Candle construction (nan/inf comparisons are
    # False) but is not valid market data, so the data-quality gate must reject.
    bad = Candle("1m", 100.0, float("inf"), 99.0, 100.0, 5.0, 60_000)  # inf high
    dataset = _mk_dataset([bad, _mk_candle(120_000)])
    dataset_path = tmp_path / "bad.json"
    dataset_path.write_text(json.dumps(dataset.to_dict(), indent=2, sort_keys=True) + "\n")
    output_path = tmp_path / "out.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_real_history.py"),
         "--dataset", str(dataset_path), "--output", str(output_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "bad_prices=" in (proc.stdout + proc.stderr)
    assert not output_path.exists()


def test_data_quality_as_dict_includes_new_fields():
    """The serialized report exposes the strengthened facts for downstream use."""
    candles = [_mk_candle(60_000 * i) for i in range(1, 11)]
    report = data_quality_report(_mk_dataset(candles), max_data_age_ms=600_000)
    d = report.as_dict()
    for key in ("bad_prices", "price_integrity_ok", "data_age_ms",
                "max_data_age_ms", "freshness_ok", "max_single_bar_return_bps",
                "funding_anomalies"):
        assert key in d
