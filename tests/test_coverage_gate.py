"""Fail-closed gap-coverage gate for historical datasets (TDD: RED first).

A dataset with large missing-bar fractions (holes in the candle series) would
distort walk-forward time indices, yet the structural ``ok`` gate ignores gaps.
This gate fails closed: reject when the missing-bar fraction exceeds a threshold
or a single hole is too large. No signed calls, no credentials, no orders. Pure
offline measurement.
"""
import pytest

from src.market.models import Candle
from src.market.history import (
    DataQualityReport,
    HistoryDataset,
    FundingRecord,
    data_quality_report,
    coverage_gate,
)


def _mk_candle(ts, close=100.0):
    return Candle("1m", 99.5, 101.0, 99.0, close, 5.0, ts)


def _mk_dataset(candles, funding=()):
    return HistoryDataset(
        symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="1m",
        fetched_at_ms=max(c.source_ts_ms for c in candles),
        candles=tuple(candles),
        funding=tuple(FundingRecord(ft, r) for ft, r in funding),
        assumed_half_spread_bps=0.5,
    )


def test_coverage_gate_rejects_sparse_dataset():
    # Two candles 10 minutes apart at 1m => 9 missing bars of 11 expected (~82%).
    candles = [_mk_candle(60_000), _mk_candle(60_000 + 10 * 60_000)]
    report = data_quality_report(_mk_dataset(candles))
    # The existing structural gate does NOT reject gaps on its own.
    assert report.ok is True
    # The coverage gate must fail closed on the sparse series.
    assert coverage_gate(report) is False


def test_coverage_gate_passes_dense_dataset():
    candles = [_mk_candle(60_000 * i) for i in range(1, 21)]
    report = data_quality_report(_mk_dataset(candles))
    assert coverage_gate(report) is True


def test_coverage_gate_rejects_moderate_sparse_with_tight_fraction():
    # 1 missing bar of 3 expected (~33%) fails a tight 0.25 threshold but passes 0.5.
    candles = [_mk_candle(60_000), _mk_candle(60_000 * 3)]
    report = data_quality_report(_mk_dataset(candles))
    assert coverage_gate(report, max_missing_fraction=0.25) is False
    assert coverage_gate(report, max_missing_fraction=0.5) is True


def test_coverage_gate_single_hole_exceeds_absolute_cap():
    # Dense body, then one ~61-bar hole, then dense tail. Fraction stays under
    # 0.25 (so the relative gate passes) but the absolute per-gap cap (50) must
    # still reject the single oversized hole.
    head = [_mk_candle(60_000 * i) for i in range(1, 101)]
    tail = [_mk_candle(60_000 * (100 + 61) + 60_000 * i) for i in range(1, 101)]
    report = data_quality_report(_mk_dataset(head + tail))
    assert report.max_missing_bars >= 60
    assert coverage_gate(report) is True              # relative fraction ok
    assert coverage_gate(report, max_single_gap_bars=50) is False


def test_coverage_gate_invalid_params():
    candles = [_mk_candle(60_000 * i) for i in range(1, 11)]
    report = data_quality_report(_mk_dataset(candles))
    with pytest.raises(ValueError):
        coverage_gate(report, max_missing_fraction=1.5)
    with pytest.raises(ValueError):
        coverage_gate(report, max_single_gap_bars=-1)
