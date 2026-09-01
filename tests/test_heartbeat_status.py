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


# Phase 50: corpus freshness must surface on the observability dashboard so a
# stale blessed corpus is VISIBLE and can park heavy evaluation work fail-closed
# (directive §7 + §11). The observation itself lives in
# src/evaluation/corpus_staleness (Phase 49, mutation-verified); here we wire it
# into assemble_status and keep the fail-closed guarantee intact.
NOW = 1_700_000_000_000  # epoch-ms in ~2023, keeps fetched_at_ms a positive int.


def test_corpus_freshness_missing_reported_stale_fail_closed(tmp_path: Path):
    from scripts.heartbeat_status import _corpus_freshness
    rep = _corpus_freshness(tmp_path / "absent", now_ms=NOW)
    assert rep["present"] is False
    assert rep["stale"] is True
    assert rep["reason"] == "no_fresh_corpus"


def test_corpus_freshness_fresh_and_stale(tmp_path: Path):
    from scripts.heartbeat_status import _corpus_freshness

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (fresh / "BTCUSDT_1m.json").write_text(
        json.dumps({"symbol": "BTCUSDT", "fetched_at_ms": NOW - 1000}))
    rep = _corpus_freshness(fresh, now_ms=NOW)
    assert rep["present"] is True
    assert rep["stale"] is False
    assert rep["reason"] == "fresh"

    old = NOW - (8 * 24 * 3600 * 1000)  # 8 days -> beyond the 7-day policy.
    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "BTCUSDT_1m.json").write_text(
        json.dumps({"symbol": "BTCUSDT", "fetched_at_ms": old}))
    rep2 = _corpus_freshness(stale, now_ms=NOW)
    assert rep2["present"] is True
    assert rep2["stale"] is True
    assert rep2["reason"] == "stale"


def test_corpus_freshness_unavailable_falls_back_fail_closed(monkeypatch, tmp_path_factory):
    # If the observation itself raises, we cannot prove freshness -> fail closed.
    from scripts.heartbeat_status import _corpus_freshness

    def _boom(*_a, **_k):
        raise RuntimeError("observation failed")
    monkeypatch.setattr(
        "scripts.heartbeat_status.evaluate_corpus_freshness", _boom)
    rep = _corpus_freshness(tmp_path_factory.mktemp("corpus"), now_ms=NOW)
    assert rep["present"] is False
    assert rep["stale"] is True
    assert rep["reason"] == "unavailable"


def test_assemble_status_surfaces_corpus_freshness(tmp_path: Path):
    from scripts.heartbeat_status import assemble_status
    status = assemble_status(tmp_path)
    assert "corpus_freshness" in status
    cf = status["corpus_freshness"]
    assert isinstance(cf, dict)
    for key in ("present", "datasets", "newest_ms", "oldest_ms", "max_age_ms",
                "stale", "reason", "fresh_ms"):
        assert key in cf, f"missing corpus_freshness key: {key}"


# Phase 51: a consumer that acts on corpus_freshness.stale to park heavy
# evaluation work fail-closed (directive §11 automation contract). When
# the blessed corpus is stale we cannot run trustworthy evaluation, so
# we park it rather than produce a questionable result.
NOW = 1_700_000_000_000


def test_should_park_returns_true_when_corpus_stale():
    from scripts.heartbeat_status import should_park_heavy_work
    status = {
        "corpus_freshness": {
            "present": True, "datasets": 3, "stale": True,
            "reason": "stale", "fresh_ms": None,
        },
    }
    assert should_park_heavy_work(status) is True


def test_should_park_returns_false_when_corpus_fresh():
    from scripts.heartbeat_status import should_park_heavy_work
    status = {
        "corpus_freshness": {
            "present": True, "datasets": 3, "stale": False,
            "reason": "fresh", "fresh_ms": 1000,
        },
    }
    assert should_park_heavy_work(status) is False


def test_should_park_returns_true_when_corpus_unavailable():
    from scripts.heartbeat_status import should_park_heavy_work
    # Observation itself raised -> we reported stale=True with reason="unavailable"
    status = {
        "corpus_freshness": {
            "present": False, "datasets": 0, "stale": True,
            "reason": "unavailable", "fresh_ms": None,
        },
    }
    assert should_park_heavy_work(status) is True


def test_should_park_fail_closed_on_malformed_status():
    from scripts.heartbeat_status import should_park_heavy_work
    # Missing key, empty dict, None -> cannot prove safe -> park (fail closed)
    assert should_park_heavy_work({}) is True
    assert should_park_heavy_work({"corpus_freshness": {}}) is True
    assert should_park_heavy_work(None) is True
