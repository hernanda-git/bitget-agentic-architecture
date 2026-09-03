"""Fail-closed corpus-staleness guard for the combined-stress report generator.

Wire should_park_heavy_work() into run_combined_stress_report.main() so the
Phase-10 stress report parks fail-closed when the blessed corpus is stale
(directive sec. 11 automation contract).
"""
from __future__ import annotations


def _fake_result(*args, **kwargs):
    return {
        "symbol": args[0] if args else "BTCUSDT",
        "granularity": args[1] if len(args) > 1 else "1m",
        "invariant_all_pass": True,
        "baseline": {"net_pnl": -100.0, "closed_trades": 10},
        "combined_stress": {"net_pnl": -100.0},
        "walk_forward_robustness": {"selection_blocked": True},
    }


def test_run_combined_stress_report_parks_when_corpus_stale(monkeypatch):
    """Fail-closed: main() returns exit code 8 when corpus freshness is stale."""
    from scripts.run_combined_stress_report import main

    stale_status = {
        "corpus_freshness": {
            "present": True, "datasets": 3, "stale": True,
            "reason": "stale", "fresh_ms": None,
        },
    }
    monkeypatch.setattr(
        "scripts.heartbeat_status.assemble_status", lambda: stale_status
    )
    # Prevent real dataset loading while proving the guard fires first.
    monkeypatch.setattr(
        "scripts.run_combined_stress_report.evaluate_one", _fake_result
    )
    # Avoid writing the report file during the test.
    monkeypatch.setattr(
        "scripts.run_combined_stress_report.Path.write_text", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "scripts.run_combined_stress_report.Path.mkdir", lambda *a, **kw: None
    )
    result = main()
    assert result == 8


def test_run_combined_stress_report_runs_when_corpus_fresh(monkeypatch):
    """Green path: main() proceeds when corpus is fresh."""
    from scripts.run_combined_stress_report import main

    fresh_status = {
        "corpus_freshness": {
            "present": True, "datasets": 3, "stale": False,
            "reason": "fresh", "fresh_ms": 1000,
        },
    }
    monkeypatch.setattr(
        "scripts.heartbeat_status.assemble_status", lambda: fresh_status
    )
    call_count = {"n": 0}

    def fake_evaluate_one(symbol, granularity):
        call_count["n"] += 1
        return _fake_result()

    monkeypatch.setattr(
        "scripts.run_combined_stress_report.evaluate_one", fake_evaluate_one
    )
    monkeypatch.setattr(
        "scripts.run_combined_stress_report.DATASETS",
        [("BTCUSDT", "1m"), ("ETHUSDT", "5m")],
    )
    monkeypatch.setattr(
        "scripts.run_combined_stress_report.Path.write_text", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "scripts.run_combined_stress_report.Path.mkdir", lambda *a, **kw: None
    )
    result = main()
    assert result == 0
    assert call_count["n"] == 2


def test_run_combined_stress_report_parks_fail_closed_on_malformed_status(monkeypatch):
    """Fail-closed: malformed/missing corpus_freshness always parks."""
    from scripts.run_combined_stress_report import main

    monkeypatch.setattr(
        "scripts.heartbeat_status.assemble_status", lambda: {}
    )
    monkeypatch.setattr(
        "scripts.run_combined_stress_report.evaluate_one", _fake_result
    )
    monkeypatch.setattr(
        "scripts.run_combined_stress_report.Path.write_text", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "scripts.run_combined_stress_report.Path.mkdir", lambda *a, **kw: None
    )
    result = main()
    assert result == 8