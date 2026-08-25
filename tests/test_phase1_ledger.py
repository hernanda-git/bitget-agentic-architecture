import sqlite3
import subprocess
import sys

import pytest

from src.ledger.events import RuntimeEvent
from src.ledger.sqlite import EventLedger


def event(**overrides):
    value = {
        "event_type": "AGENT_DECISION",
        "cycle_id": "c1",
        "trace_id": "t1",
        "created_ms": 1700000000000,
        "mode": "paper",
        "product_type": "SUSDT-FUTURES",
        "symbol": "BTCUSDT",
        "payload": {"action": "ENTER"},
        "market_snapshot_id": "ms-1",
        "market_snapshot_hash": "mh-1",
        "context_hash": "ctx-1",
        "provider": "fake",
        "model": "fixture",
        "prompt_version": "p1",
        "decision_hash": "dh-1",
        "policy_version": "policy-1",
        "strategy_version": "strategy-1",
        "intent_id": "intent-1",
        "client_order_id": "co-1",
        "venue_order_id": "vo-1",
        "fill_ids": ["fill-1"],
        "position_snapshot_id": "pos-1",
        "protection_snapshot_id": "prot-1",
    }
    value.update(overrides)
    return value


def test_canonical_event_preserves_immutable_run_metadata():
    item = RuntimeEvent.from_dict(event())
    assert item.to_dict()["market_snapshot_hash"] == "mh-1"
    assert item.to_dict()["intent_id"] == "intent-1"
    assert item.to_dict()["fill_ids"] == ["fill-1"]


def test_append_rejects_unvalidated_unknown_event():
    ledger = EventLedger(__import__("pathlib").Path("/tmp/phase1-event-test.sqlite3"))
    with pytest.raises(ValueError):
        ledger.append("NOT_A_RUNTIME_EVENT", {})


def test_event_and_projection_commit_atomically(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    with pytest.raises(RuntimeError):
        ledger.append_event_with_projection(event(), "positions", {"position_id": "pos-1", "status": "OPEN"},
                                             fault_injector=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ledger.all() == []
    assert ledger.table_rows("positions") == []


def test_sqlite_runtime_pragmas_and_migration_version(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    with ledger._connect() as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
        assert db.execute("SELECT version FROM schema_migrations").fetchone()[0] >= 1


def test_required_financial_and_breaker_queries(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    assert ledger.closed_trades() == []
    assert ledger.realized_pnl() == 0.0
    assert ledger.fees() == 0.0
    assert ledger.funding() == 0.0
    assert ledger.active_breakers() == []
    assert ledger.runtime_status()["latest_cycle"] is None


def test_replay_script_runs_directly_from_repository_root(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/replay_ledger.py", str(tmp_path / "empty.sqlite3")],
        cwd=__import__("pathlib").Path(__file__).resolve().parents[1],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
