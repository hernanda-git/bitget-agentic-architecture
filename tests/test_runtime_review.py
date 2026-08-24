from src.reviews.runtime_review import (
    REQUIRED_CHANGE_CHECKS,
    evaluate_change_gate,
    evaluate_rollback,
    review_run,
)


def good_report():
    return {
        "run_id": "run-1", "mode": "paper", "status": "PASS", "integrity_ok": True,
        "network_calls": 0, "signed_calls": 0, "degraded_states": [],
        "duplicate_prevention": {"duplicate_events": 0, "ledger_claims": 2},
        "provider": {"calls": 2, "failures": 0},
        "protection_reconciliation": {"reconciled": 2, "verified": 2},
        "ui": {"mode": "demo-readonly", "writable": False,
               "responsive": {"360x800": True, "390x844": True, "768x844": True,
                               "1024x900": True, "1440x900": True},
               "sources": ["ledger", "demo venue"]},
    }


def good_ledger():
    return {"integrity_ok": True, "schema_version": 1, "events": [
        {"event_type": "MARKET_OBSERVED", "cycle_id": "c1", "payload_hash": "a"},
        {"event_type": "CYCLE_TERMINAL", "cycle_id": "c1", "payload_hash": "b"},
    ], "duplicate_events": 0}


def test_review_has_three_independent_passing_sections_with_evidence_and_risks():
    result = review_run(good_report(), good_ledger())
    assert set(result.sections) == {"safety_execution", "data_integrity_ledger", "ui_truthfulness_responsive"}
    assert all(section.status == "PASS" for section in result.sections.values())
    assert all(section.evidence for section in result.sections.values())
    assert all(isinstance(section.risks, list) for section in result.sections.values())


def test_review_blocks_safety_and_keeps_negative_evidence():
    report = good_report()
    report["provider"]["failures"] = 2
    report["degraded_states"] = ["PROTECTION_DEGRADED"]
    result = review_run(report, good_ledger())
    section = result.sections["safety_execution"]
    assert section.status == "BLOCK"
    assert any("failures=2" in item for item in section.evidence)
    assert any("PROTECTION_DEGRADED" in item for item in section.risks)


def test_review_blocks_ledger_and_ui_independently():
    report = good_report()
    report["ui"]["writable"] = True
    ledger = good_ledger()
    ledger["integrity_ok"] = False
    result = review_run(report, ledger)
    assert result.sections["data_integrity_ledger"].status == "BLOCK"
    assert result.sections["ui_truthfulness_responsive"].status == "BLOCK"


def test_change_gate_requires_every_check_for_demo_execution():
    checks = {name: True for name in REQUIRED_CHANGE_CHECKS}
    gate = evaluate_change_gate(checks, version="provider-v2", enable_demo_execution=True)
    assert gate.status == "PASS"
    checks["ui"] = False
    gate = evaluate_change_gate(checks, version="provider-v2", enable_demo_execution=True)
    assert gate.status == "BLOCK"
    assert "ui" in gate.missing_checks
    assert gate.version == "provider-v2"


def test_change_gate_does_not_allow_implicit_demo_enablement():
    gate = evaluate_change_gate({}, version="prompt-v1")
    assert gate.status == "BLOCK"
    assert set(gate.missing_checks) == set(REQUIRED_CHANGE_CHECKS)


def test_rollback_parks_on_any_unsafe_signal_and_passes_when_clear():
    assert evaluate_rollback({"provider_errors": True}) == "PARKED"
    assert evaluate_rollback({"stale_data": True}) == "PARKED"
    assert evaluate_rollback({"duplicate_risk": True}) == "PARKED"
    assert evaluate_rollback({key: False for key in (
        "provider_errors", "stale_data", "ledger_integrity_failure",
        "protection_degradation", "reconciliation_drift", "heartbeat_expiry",
        "duplicate_risk")}) == "CLEAR"
