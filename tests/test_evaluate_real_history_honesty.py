"""Fail-closed truthfulness wiring for ``evaluate_real_history.py`` (TDD: RED first).

Mirrors the phase-15 honesty anchor already wired into
``scripts/run_strategy_baseline.py``, but for the real-history entrypoint. The
entrypoint must:

* carry a ``selection_blocked=True`` honesty anchor in the emitted payload,
* call ``assert_truthful(payload)`` BEFORE writing the report,
* fail closed (no report written, dedicated nonzero exit) when any overclaim is
  present in the assembled payload.

Unblocked work: dashboard truthfulness parity. Pure measurement; never changes
the deterministic promotion gate or selection. No network, no credentials, no
orders. The synthetic dataset is contiguous and short (no funding settlements
are expected across its span), so every upstream fail-closed gate
(``data_quality_report``, ``gate_walk_forward_dataset``, ``real_funding_readiness``)
passes and control reaches the honesty step.
"""
from pathlib import Path
import json
import subprocess
import sys

import pytest

from src.market.models import Candle
from src.market.history import HistoryDataset
from src.evaluation.report_honesty import (
    ReportHonestyError,
    assert_truthful,
    find_overclaims,
)

ROOT = Path(__file__).resolve().parents[1]


def _mk_contiguous(symbol="BTCUSDT", n=90, step_ms=60_000,
                   base_ts=1_700_000_000_000, start_close=100.0):
    candles = []
    for i in range(n):
        c = start_close + i * 0.1
        candles.append(Candle("1m", c - 0.5, c + 1.0, c - 1.0, c, 10.0,
                              base_ts + i * step_ms))
    return candles


def _mk_dataset(candles):
    # Short span -> no funding settlements expected -> funding readiness ok.
    return HistoryDataset(
        symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="1m",
        fetched_at_ms=max(c.source_ts_ms for c in candles),
        candles=tuple(candles),
        funding=tuple(),
        assumed_half_spread_bps=0.5,
    )


def _write_dataset(tmp_path: Path) -> Path:
    ds = _mk_dataset(_mk_contiguous())
    dataset_path = tmp_path / "synthetic.json"
    dataset_path.write_text(json.dumps(ds.to_dict(), indent=2, sort_keys=True) + "\n")
    return dataset_path


def test_honest_real_history_report_carries_honesty_anchor_and_passes_guard(tmp_path):
    """The real entrypoint writes a truthful report carrying ``selection_blocked=True``."""
    dataset_path = _write_dataset(tmp_path)
    output_path = tmp_path / "out.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_real_history.py"),
         "--dataset", str(dataset_path), "--output", str(output_path),
         "--no-resource-budget"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert output_path.exists()
    payload = json.loads(output_path.read_text())
    # Honesty anchor present (RED before wiring: missing -> assertion fails).
    assert payload.get("selection_blocked") is True
    assert payload.get("report_honest") is True
    # The emitted report is genuinely truthful (real guard over the real payload).
    assert find_overclaims(payload) == []
    assert_truthful(payload)


def test_overclaim_fails_closed_without_writing_report(tmp_path, monkeypatch):
    """A detected overclaim must abort before writing; the guard sits in the path."""
    import scripts.evaluate_real_history as mod
    dataset_path = _write_dataset(tmp_path)
    output_path = tmp_path / "out.json"

    calls = []

    def fake_truthful(report):
        calls.append(report)
        raise ReportHonestyError("injected overclaim")

    monkeypatch.setattr(
        "sys.argv",
        ["evaluate_real_history.py", "--dataset", str(dataset_path),
         "--output", str(output_path), "--no-resource-budget"],
    )
    monkeypatch.setattr(mod, "assert_truthful", fake_truthful)
    rc = mod.main()
    # Guard was actually invoked on the assembled payload (RED before wiring: never called).
    assert calls, "assert_truthful was never invoked in the write path"
    assert calls[0].get("selection_blocked") is True
    # Fail closed: no report written, dedicated nonzero exit.
    assert rc != 0
    assert not output_path.exists()
