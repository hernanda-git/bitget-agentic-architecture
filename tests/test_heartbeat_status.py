"""Heartbeat status aggregator (Phase 47, TDD).

Records each autonomous tick into a durable JSONL log + a `last.json` snapshot and
assembles a read-only status projection (git, phase reports, factor ontology
coverage, resource guard, latest tick) for the observability dashboard.

Fail-closed: missing artifacts are reported as absent, never invented. No secrets,
no /opt/bots/bitget-listener, no signed/order calls — pure local reads.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.heartbeat_status import (
    DEFAULT_STATE_DIR,
    assemble_status,
    derive_next_run,
    load_history,
    record_tick,
)


def test_record_tick_writes_last_json_and_appends_history(tmp_path: Path):
    rec = record_tick(
        tmp_path,
        tick_id="tick-1",
        phase="Phase 46",
        summary="did work",
        passed=638, failed=0, skipped=4,
        baseline_negative=True,
        commit="deadbeef",
        pushed=True,
    )
    last = json.loads((tmp_path / "last.json").read_text())
    assert last["tick_id"] == "tick-1"
    assert last["phase"] == "Phase 46"
    assert last["passed"] == 638 and last["failed"] == 0
    assert last["baseline_negative"] is True
    assert last["commit"] == "deadbeef" and last["pushed"] is True
    assert isinstance(rec["recorded_at_ms"], int)
    # History is append-only JSONL, one line per tick.
    history = load_history(tmp_path)
    assert len(history) == 1
    assert history[0]["tick_id"] == "tick-1"


def test_record_tick_appends_without_clobbering(tmp_path: Path):
    record_tick(tmp_path, tick_id="a", phase="P1", summary="s", passed=1, failed=0, skipped=0)
    record_tick(tmp_path, tick_id="b", phase="P2", summary="s", passed=2, failed=0, skipped=0)
    history = load_history(tmp_path)
    assert [h["tick_id"] for h in history] == ["a", "b"]
    # last.json tracks the most recent tick only.
    assert json.loads((tmp_path / "last.json").read_text())["tick_id"] == "b"


def test_assemble_status_never_exposes_secrets_or_opt_bots(tmp_path: Path):
    record_tick(tmp_path, tick_id="x", phase="Phase 47", summary="ok", passed=638, failed=0, skipped=4,
                baseline_negative=True, commit="abc", pushed=True)
    status = assemble_status(tmp_path)
    blob = json.dumps(status)
    assert "api_key" not in blob and "secret" not in blob and "token" not in blob
    assert "/opt/bots/bitget-listener" not in blob
    # Required top-level keys for the dashboard.
    for key in ("mode", "repo", "git", "latest_tick", "history", "phase_reports",
                "factor_ontology", "resource_guard", "next_scheduled_run"):
        assert key in status, f"missing status key: {key}"
    assert status["mode"] == "readonly-observability"
    assert status["factor_ontology"]["promotion_ready"] is False or isinstance(
        status["factor_ontology"]["promotion_ready"], bool)


def test_assemble_status_reports_missing_artifacts_fail_closed(tmp_path: Path):
    # No ticks recorded yet -> latest_tick is None, history empty, not invented.
    status = assemble_status(tmp_path)
    assert status["latest_tick"] is None
    assert status["history"] == []
    # Git read resolves against the real repo root (not the tmp dir), so it is
    # truthful about the real checkout rather than fabricated as absent.
    assert status["git"]["path_present"] is True
    assert status["git"]["commit"] != ""


def test_derive_next_run_is_next_six_hour_boundary():
    # 2026-08-30 16:39:00 UTC -> next 6h boundary is 18:00.
    import datetime as _dt
    now = _dt.datetime(2026, 8, 30, 16, 39, 0, tzinfo=_dt.timezone.utc)
    nxt = derive_next_run(now)
    assert nxt == _dt.datetime(2026, 8, 30, 18, 0, 0, tzinfo=_dt.timezone.utc)
    # Just after a boundary (18:01) -> next is 00:00 next day.
    nxt2 = derive_next_run(_dt.datetime(2026, 8, 30, 18, 1, 0, tzinfo=_dt.timezone.utc))
    assert nxt2 == _dt.datetime(2026, 8, 31, 0, 0, 0, tzinfo=_dt.timezone.utc)
