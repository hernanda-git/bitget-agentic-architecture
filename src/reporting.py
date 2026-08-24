"""Small, deterministic JSON and Markdown reporting for offline runs."""
from __future__ import annotations

import json
from pathlib import Path


def write_run_report(report: dict, reports_dir: Path) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_id = report["run_id"]
    json_path = reports_dir / f"run-{run_id}.json"
    md_path = reports_dir / f"run-{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    counts = report.get("counts", {})
    lines = [f"# Offline {report['mode']} run `{run_id}`", "", f"- Status: `{report['status']}`",
             f"- Integrity OK: `{report['integrity_ok']}`", f"- Cycles: `{counts.get('cycles', 0)}`",
             f"- Orders placed: `{report.get('orders_placed', 0)}`",
             f"- Signed calls: `{report.get('signed_calls', 0)}`", "", "## Counts", ""]
    lines.extend(f"- {key}: {value}" for key, value in sorted(counts.items()))
    lines += ["", "## Rejections", ""]
    rejection_lines = [f"- {key}: {value}" for key, value in sorted(report.get("rejection_codes", {}).items())]
    lines += rejection_lines or ["- none"]
    lines += ["", "## Safety evidence", "", f"- Degraded states: `{report.get('degraded_states', [])}`",
              f"- Duplicate prevention: `{report.get('duplicate_prevention', {})}`",
              f"- Protection/reconciliation: `{report.get('protection_reconciliation', {})}`",
              f"- Provider: `{report.get('provider', {})}`",
              f"- Fee-inclusive paper outcome: `{report.get('fee_inclusive_outcome', {})}`",
              f"- Anomalies: `{report.get('anomalies', [])}`", ""]
    md_path.write_text("\n".join(lines))
    return json_path, md_path
