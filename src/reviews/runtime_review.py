"""Deterministic, network-free Phase G review helpers.

The module deliberately treats missing evidence as a block. It accepts either
already-loaded mappings or paths to JSON files, which keeps the CLI and callers
on the same code path.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

REQUIRED_CHANGE_CHECKS = (
    "fixture_replay", "paper", "schema", "policy", "protection",
    "reconciliation", "ui",
)
ROLLBACK_SIGNALS = (
    "provider_errors", "stale_data", "ledger_integrity_failure",
    "protection_degradation", "reconciliation_drift", "heartbeat_expiry",
    "duplicate_risk",
)


@dataclass(frozen=True)
class ReviewSection:
    status: str
    evidence: list[str]
    risks: list[str]


@dataclass(frozen=True)
class ReviewResult:
    sections: dict[str, ReviewSection]

    @property
    def status(self) -> str:
        return "PASS" if all(s.status == "PASS" for s in self.sections.values()) else "BLOCK"

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "sections": {k: asdict(v) for k, v in self.sections.items()}}


@dataclass(frozen=True)
class ChangeGateResult:
    status: str
    version: str
    required_checks: tuple[str, ...]
    missing_checks: list[str]
    evidence: list[str]

    @property
    def allowed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"allowed": self.allowed}


def _load(value: Mapping[str, Any] | list[Any] | str | Path) -> Any:
    if isinstance(value, (str, Path)):
        return json.loads(Path(value).read_text())
    return value


def _flag(value: Any) -> bool:
    return bool(value)


def _section(status: bool, evidence: list[str], risks: list[str]) -> ReviewSection:
    return ReviewSection("PASS" if status else "BLOCK", evidence, risks)


def review_run(report: Mapping[str, Any] | str | Path,
               ledger: Mapping[str, Any] | list[Any] | str | Path) -> ReviewResult:
    """Review a run report and ledger in three independent truth domains."""
    report = _load(report)
    ledger = _load(ledger)
    if not isinstance(report, Mapping):
        raise TypeError("report must be a JSON object")

    provider = report.get("provider") or {}
    duplicate = report.get("duplicate_prevention") or {}
    protection = report.get("protection_reconciliation") or {}
    degraded = report.get("degraded_states") or []
    safety_evidence = [
        f"report.status={report.get('status', '<missing>')}",
        f"integrity_ok={report.get('integrity_ok', '<missing>')}",
        f"network_calls={report.get('network_calls', '<missing>')}",
        f"signed_calls={report.get('signed_calls', '<missing>')}",
        f"provider.failures={provider.get('failures', '<missing>')}",
        f"duplicate_events={duplicate.get('duplicate_events', '<missing>')}",
        f"protection_reconciliation={protection}",
    ]
    safety_risks = [f"degraded_state={item}" for item in degraded]
    if report.get("integrity_ok") is not True:
        safety_risks.append(f"run integrity is not true: {report.get('integrity_ok', '<missing>')}")
    if _flag(report.get("network_calls")) or _flag(report.get("signed_calls")):
        safety_risks.append("network or signed calls were recorded")
    if provider.get("failures", 0) != 0:
        safety_risks.append(f"provider failures={provider.get('failures')}")
    if duplicate.get("duplicate_events", 0) != 0:
        safety_risks.append(f"duplicate events={duplicate.get('duplicate_events')}")
    safety_ok = (report.get("status") == "PASS" and report.get("integrity_ok") is True
                 and report.get("network_calls", 0) == 0 and report.get("signed_calls", 0) == 0
                 and not degraded and provider.get("failures", 0) == 0
                 and duplicate.get("duplicate_events", 0) == 0)

    if isinstance(ledger, list):
        ledger_obj: Mapping[str, Any] = {"events": ledger}
    elif isinstance(ledger, Mapping):
        ledger_obj = ledger
    else:
        raise TypeError("ledger must be a JSON object or event list")
    events = ledger_obj.get("events") or []
    data_risks: list[str] = []
    if ledger_obj.get("integrity_ok") is not True:
        data_risks.append(f"ledger integrity is not true: {ledger_obj.get('integrity_ok', '<missing>')}")
    if ledger_obj.get("duplicate_events", 0) != 0:
        data_risks.append(f"ledger duplicate_events={ledger_obj.get('duplicate_events')}")
    if not events:
        data_risks.append("ledger contains no events")
    missing_identity = [str(i) for i, event in enumerate(events)
                        if not isinstance(event, Mapping) or not event.get("cycle_id")
                        or not event.get("payload_hash")]
    if missing_identity:
        data_risks.append(f"events missing cycle_id or payload_hash at indexes={missing_identity}")
    data_evidence = [
        f"ledger.integrity_ok={ledger_obj.get('integrity_ok', '<missing>')}",
        f"ledger.schema_version={ledger_obj.get('schema_version', '<missing>')}",
        f"ledger.events={len(events)}",
        f"ledger.duplicate_events={ledger_obj.get('duplicate_events', '<missing>')}",
    ]
    data_ok = (ledger_obj.get("integrity_ok") is True and ledger_obj.get("schema_version") is not None
               and bool(events) and not missing_identity and ledger_obj.get("duplicate_events", 0) == 0)

    ui = report.get("ui") or report.get("ui_projection")
    ui_risks: list[str] = []
    if not isinstance(ui, Mapping):
        ui_risks.append("UI evidence is missing")
        ui = {}
    if ui.get("mode") != "demo-readonly":
        ui_risks.append(f"UI mode is not demo-readonly: {ui.get('mode', '<missing>')}")
    if ui.get("writable") is not False:
        ui_risks.append(f"UI writable flag is not false: {ui.get('writable', '<missing>')}")
    responsive = ui.get("responsive") or {}
    bad_viewports = [viewport for viewport, passed in responsive.items() if passed is not True]
    if not responsive:
        ui_risks.append("responsive checks are missing")
    elif bad_viewports:
        ui_risks.append(f"responsive checks failed: {bad_viewports}")
    if not ui.get("sources"):
        ui_risks.append("UI source labels are missing")
    ui_evidence = [
        f"ui.mode={ui.get('mode', '<missing>')}", f"ui.writable={ui.get('writable', '<missing>')}",
        f"ui.responsive={responsive}", f"ui.sources={ui.get('sources', '<missing>')}",
    ]
    ui_ok = (ui.get("mode") == "demo-readonly" and ui.get("writable") is False
             and bool(responsive) and not bad_viewports and bool(ui.get("sources")))

    return ReviewResult({
        "safety_execution": _section(safety_ok, safety_evidence, safety_risks),
        "data_integrity_ledger": _section(data_ok, data_evidence, data_risks),
        "ui_truthfulness_responsive": _section(ui_ok, ui_evidence, ui_risks),
    })


def evaluate_change_gate(checks: Mapping[str, Any] | None = None, *, version: str,
                         enable_demo_execution: bool = False, **check_kwargs: Any) -> ChangeGateResult:
    """Require every offline verification before a version may enable demo execution."""
    merged = dict(checks or {})
    merged.update(check_kwargs)
    missing = [name for name in REQUIRED_CHANGE_CHECKS if merged.get(name) is not True]
    if not version:
        missing.append("version")
    evidence = [f"{name}={'PASS' if name not in missing else 'BLOCK'}" for name in REQUIRED_CHANGE_CHECKS]
    evidence.append(f"version={'PASS' if version else 'BLOCK'}")
    status = "PASS" if not missing else "BLOCK"
    if enable_demo_execution and missing:
        evidence.append("demo execution enablement denied because required checks are incomplete")
    return ChangeGateResult(status, version, REQUIRED_CHANGE_CHECKS, missing, evidence)


def evaluate_rollback(signals: Mapping[str, Any] | None = None, **signal_kwargs: Any) -> str:
    """Return PARKED if any listed unsafe runtime signal is active."""
    merged = dict(signals or {})
    merged.update(signal_kwargs)
    return "PARKED" if any(_flag(merged.get(name)) for name in ROLLBACK_SIGNALS) else "CLEAR"


# Descriptive aliases for callers that prefer noun-oriented names.
review_report = review_run
change_gate = evaluate_change_gate
rollback_status = evaluate_rollback
rollback_if_unsafe = evaluate_rollback
