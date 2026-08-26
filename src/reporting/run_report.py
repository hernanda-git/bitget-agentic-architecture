"""Durable evidence reports for bounded offline paper runs."""
from __future__ import annotations

import json
import os
import resource
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Mapping

JAKARTA = timezone(timedelta(hours=7), name="Asia/Jakarta")


def jakarta_timestamp(started_ms: int) -> str:
    return datetime.fromtimestamp(started_ms / 1000, tz=JAKARTA).isoformat()


def resource_snapshot() -> dict[str, Any]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    disk = shutil.disk_usage(Path.cwd())
    available = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                available = int(line.split()[1]) * 1024
                break
    except (OSError, ValueError):
        pass
    return {
        "available_memory_bytes": available,
        "max_rss_bytes": int(usage.ru_maxrss * 1024),
        "disk_free_bytes": int(disk.free),
        "pid": os.getpid(),
    }


def build_paper_run_report(*, run_id: str, started_ms: int,
                           ledger_counts: Mapping[str, int],
                           rejection_codes: Mapping[str, int] | None = None,
                           degraded_states: list[str] | None = None,
                           provider: Mapping[str, Any] | None = None,
                           duplicate_prevention: Mapping[str, Any] | None = None,
                           protection_reconciliation: Mapping[str, Any] | None = None,
                           outcome: Mapping[str, Any] | None = None,
                           anomalies: list[str] | None = None,
                           resource_snapshot_data: Mapping[str, Any] | None = None,
                           resource_snapshot: Mapping[str, Any] | None = None,
                           next_gate: str = "RESEARCH_GATE") -> dict[str, Any]:
    return {
        "run_id": run_id,
        "timestamp": jakarta_timestamp(started_ms),
        "timestamp_timezone": "Asia/Jakarta",
        "raw_ledger_counts": dict(ledger_counts),
        "rejection_codes": dict(rejection_codes or {}),
        "degraded_states": list(degraded_states or []),
        "provider": dict(provider or {}),
        "duplicate_prevention": dict(duplicate_prevention or {}),
        "protection_reconciliation": dict(protection_reconciliation or {}),
        "fee_inclusive_outcome": dict(outcome or {}),
        "anomalies": list(anomalies or []),
        "resource_snapshot": dict(resource_snapshot_data or resource_snapshot or globals()["resource_snapshot"]()),
        "next_gate": next_gate,
    }


def write_paper_run_report(report: Mapping[str, Any], reports_dir: Path) -> tuple[Path, Path]:
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report["run_id"])
    json_path = reports_dir / f"run-{run_id}.json"
    md_path = reports_dir / f"run-{run_id}.md"
    json_path.write_text(json.dumps(dict(report), indent=2, sort_keys=True) + "\n")
    lines = [f"# Offline paper run `{run_id}`", "",
             f"- Timestamp: `{report['timestamp']}` ({report['timestamp_timezone']})",
             f"- Next gate: `{report['next_gate']}`", "", "## Evidence", ""]
    for field in ("raw_ledger_counts", "rejection_codes", "degraded_states", "provider",
                  "duplicate_prevention", "protection_reconciliation", "fee_inclusive_outcome",
                  "anomalies", "resource_snapshot"):
        lines.append(f"- {field}: `{report[field]}`")
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path
