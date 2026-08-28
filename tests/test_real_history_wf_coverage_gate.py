"""Fail-closed walk-forward coverage gate inside evaluate_real_history (TDD: RED first).

A dataset that yields too few / too-short walk-forward test windows cannot support
a statistically meaningful out-of-sample verdict, yet the engine will happily trade
a handful of bars and laud the aggregate. When ``--require-wf-coverage`` is set, the
real-history runner must fail closed (exit 6) instead of laundering a thin-corpus
aggregate. When the flag is NOT set, the coverage verdict is still reported in the
payload (measurement only) and the run proceeds.

No network, no signed calls, no orders. Fully offline (synthetic in-repo datasets).
"""
from pathlib import Path
import json
import sys

import pytest
from _pytest.monkeypatch import MonkeyPatch

from src.market.models import Candle
from src.market.history import HistoryDataset, FundingRecord
from src.evaluation.baseline import BaselineConfig
from src.evaluation.walk_forward_coverage import (
    WalkForwardCoverage,
    plan_walk_forward_coverage,
    require_wf_coverage_exit_code,
)
import scripts.evaluate_real_history as erh


def _mk_contiguous(symbol="BTCUSDT", n=60, step_ms=60_000, base_ts=1_700_000_000_000,
                   start_close=100.0):
    candles = []
    for i in range(n):
        c = start_close + i * 0.1
        candles.append(Candle("1m", c - 0.5, c + 1.0, c - 1.0, c, 10.0, base_ts + i * step_ms))
    return candles


def _mk_dataset(candles, funding=(), fetched_at_ms=None):
    if fetched_at_ms is None:
        fetched_at_ms = (max(c.source_ts_ms for c in candles) if candles
                         else 1_700_000_000_000)
    return HistoryDataset(
        symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="1m",
        fetched_at_ms=fetched_at_ms, candles=tuple(candles),
        funding=tuple(FundingRecord(ft, rate) for ft, rate in funding),
        assumed_half_spread_bps=0.5,
    )


def test_require_coverage_exit_code_short_inadequate():
    """120 bars at the default 10-bar window yield < 5 adequate windows -> reject (6)."""
    ds = _mk_dataset(_mk_contiguous(n=120))
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=10)
    rc = require_wf_coverage_exit_code(ds, config, min_windows=5, min_bars_per_window=50)
    assert rc == 6


def test_require_coverage_exit_code_long_adequate():
    """2500 bars at a 50-bar window yield >= 5 adequate windows -> pass (0)."""
    ds = _mk_dataset(_mk_contiguous(n=2500))
    config = BaselineConfig(train_fraction=0.6, embargo=1, test_window=50)
    rc = require_wf_coverage_exit_code(ds, config, min_windows=5, min_bars_per_window=50)
    assert rc == 0


def test_runner_rejects_short_dataset_with_require_flag(tmp_path):
    """The real-history entrypoint fails closed (exit 6, no report) on a thin corpus."""
    ds = _mk_dataset(_mk_contiguous(n=120))
    p = tmp_path / "SHORT_1m.json"
    p.write_text(json.dumps(ds.to_dict(), indent=2, sort_keys=True) + "\n")
    out = tmp_path / "out.json"
    argv = ["evaluate_real_history.py", "--dataset", str(p),
            "--require-wf-coverage", "--min-wf-windows", "5",
            "--min-wf-bars-per-window", "50", "--output", str(out),
            "--no-resource-budget"]
    mp = MonkeyPatch()
    with mp.context() as m:
        m.setattr(sys, "argv", argv)
        rc = erh.main()
    mp.undo()
    assert rc == 6
    assert not out.exists()  # fail-closed: no report emitted for an unverifiable corpus


def test_runner_reports_coverage_when_not_required(tmp_path):
    """Coverage verdict is always reported in the payload; the run is not blocked."""
    ds = _mk_dataset(_mk_contiguous(n=120))
    p = tmp_path / "SHORT_1m.json"
    p.write_text(json.dumps(ds.to_dict(), indent=2, sort_keys=True) + "\n")
    out = tmp_path / "out.json"
    argv = ["evaluate_real_history.py", "--dataset", str(p),
            "--output", str(out), "--no-resource-budget"]
    mp = MonkeyPatch()
    with mp.context() as m:
        m.setattr(sys, "argv", argv)
        rc = erh.main()
    mp.undo()
    assert rc == 0
    payload = json.loads(out.read_text())
    assert "walk_forward_coverage" in payload
    cov = payload["walk_forward_coverage"]
    assert cov["windows"] < 5
    assert cov["adequate"] is False
    assert cov["selection_blocked"] is True


def test_runner_adequate_when_test_window_large_enough(tmp_path):
    """2500 bars at a 50-bar window with --require-wf-coverage passes (exit 0).

    Exposes the runner's test window so the fail-closed gate is actually usable:
    with the default config ``test_window=10`` the gate can never pass (10 < the
    default min_bars_per_window=50), so a --test-window flag is required to point
    the runner at a long-enough window. Without the flag this test fails (argparse
    rejects --test-window), proving the gate was previously unusable, not just safe.

    The synthetic 2500-bar series spans ~5 eight-hour funding settlements, so it must
    carry in-range funding records or the separate funding-coverage gate rejects first;
    here we supply funding at the settlement times so the walk-forward coverage verdict
    (not the funding gate) is what this test asserts.
    """
    base_ts = 1_700_000_000_000
    funding = [(base_ts + k * 480 * 60_000, 0.0001) for k in range(1, 6)]
    ds = _mk_dataset(_mk_contiguous(n=2500), funding=funding)
    p = tmp_path / "LONG_1m.json"
    p.write_text(json.dumps(ds.to_dict(), indent=2, sort_keys=True) + "\n")
    out = tmp_path / "out.json"
    argv = ["evaluate_real_history.py", "--dataset", str(p),
            "--require-wf-coverage", "--test-window", "50",
            "--min-wf-windows", "5", "--min-wf-bars-per-window", "50",
            "--output", str(out), "--no-resource-budget"]
    mp = MonkeyPatch()
    with mp.context() as m:
        m.setattr(sys, "argv", argv)
        rc = erh.main()
    mp.undo()
    assert rc == 0
    assert out.exists()
    payload = json.loads(out.read_text())
    cov = payload["walk_forward_coverage"]
    assert cov["adequate"] is True
    assert cov["test_bars_per_window"] == 50
    assert cov["selection_blocked"] is True
