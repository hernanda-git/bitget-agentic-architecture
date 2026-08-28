"""R1: ledger must scope PnL/projection to a run so cross-version data never mixes.

RED first: these assertions must fail against the current unbounded SUM ledger.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.ledger.sqlite import EventLedger


def _seed_two_runs(path: Path) -> None:
    # Run A: legacy-ish cycle, positive net pnl + a fill fee
    la = EventLedger(path, run_id="runA")
    la.append_legacy("TRADE_CLOSED", {"cycle_id": "c1", "symbol": "BTCUSDT",
                                      "net_pnl": 100.0, "gross_pnl": 110.0,
                                      "entry_fee": 5.0, "exit_fee": 5.0, "funding": 0.0})
    la.append_legacy("FILL_OBSERVED", {"cycle_id": "c1", "symbol": "BTCUSDT",
                                      "fill_id": "fA", "client_order_id": "coA",
                                      "side": "BUY", "quantity": 1, "price": 100, "fee": 10.0, "funding": 0.0})
    # Run B: different cycle, negative net pnl + a different fill fee
    lb = EventLedger(path, run_id="runB")
    lb.append_legacy("TRADE_CLOSED", {"cycle_id": "c2", "symbol": "BTCUSDT",
                                      "net_pnl": -40.0, "gross_pnl": 10.0,
                                      "entry_fee": 25.0, "exit_fee": 25.0, "funding": 0.0})
    lb.append_legacy("FILL_OBSERVED", {"cycle_id": "c2", "symbol": "BTCUSDT",
                                      "fill_id": "fB", "client_order_id": "coB",
                                      "side": "BUY", "quantity": 1, "price": 100, "fee": 50.0, "funding": 0.0})


def test_event_stores_run_id(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    EventLedger(path, run_id="runA").append_legacy("TRADE_CLOSED", {"cycle_id": "c1", "symbol": "X", "net_pnl": 1.0})
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT run_id FROM events ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None and row[0] == "runA"


def test_realized_pnl_is_run_scoped_not_cumulative(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    _seed_two_runs(path)
    runA = EventLedger(path, run_id="runA")
    # Only run A's trade should count: +100, not +60 (mixed).
    assert runA.realized_pnl(run_id="runA") == 100.0
    assert runA.realized_pnl(run_id="runB") == -40.0


def test_fees_are_run_scoped(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    _seed_two_runs(path)
    runA = EventLedger(path, run_id="runA")
    assert runA.fees(run_id="runA") == 10.0
    assert runA.fees(run_id="runB") == 50.0


def test_runtime_status_accepts_run_id(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    _seed_two_runs(path)
    runA = EventLedger(path, run_id="runA")
    status = runA.runtime_status(run_id="runA")
    assert status["realized_pnl"] == 100.0
    assert status["fees"] == 10.0


def test_reset_clears_all_rows(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    _seed_two_runs(path)
    EventLedger(path, run_id="runC").reset()
    with sqlite3.connect(path) as db:
        n_events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        n_cycles = db.execute("SELECT COUNT(*) FROM cycles").fetchone()[0]
    assert n_events == 0 and n_cycles == 0
