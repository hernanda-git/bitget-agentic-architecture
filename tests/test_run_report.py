from datetime import datetime

from src.reporting.run_report import build_paper_run_report, write_paper_run_report


def test_paper_run_report_contains_durable_phase6_evidence(tmp_path):
    report = build_paper_run_report(
        run_id="run-test",
        started_ms=0,
        ledger_counts={"CYCLE_TERMINAL": 2},
        rejection_codes={"HOLD": 1},
        degraded_states=["PROVIDER_OUTAGE"],
        provider={"calls": 2, "failures": 1, "latency_ms": {"p50": 3}},
        duplicate_prevention={"duplicate_orders_prevented": 1},
        protection_reconciliation={"protection_verified": 1, "reconciliation_checks": 2},
        outcome={"fees_paid": 0.1, "realized_pnl": 1.2, "net_pnl_after_fees": 1.1},
        anomalies=["INTERRUPTED_CYCLE_RECOVERED"],
        resource_snapshot={"available_memory_bytes": 123},
        next_gate="RESEARCH_GATE",
    )
    assert report["run_id"] == "run-test"
    assert report["timestamp_timezone"] == "Asia/Jakarta"
    assert report["timestamp"].endswith("+07:00")
    for field in ("raw_ledger_counts", "rejection_codes", "degraded_states", "provider",
                  "duplicate_prevention", "protection_reconciliation", "fee_inclusive_outcome",
                  "anomalies", "resource_snapshot", "next_gate"):
        assert field in report

    paths = write_paper_run_report(report, tmp_path)
    assert all(path.exists() for path in paths)
    assert "Asia/Jakarta" in paths[1].read_text()
