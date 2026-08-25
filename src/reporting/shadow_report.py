"""Metrics-first reports for fixture and public shadow runs."""
from __future__ import annotations

import json
from pathlib import Path


def write_shadow_report(report: dict, reports_dir: Path) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    lines = [f"# {report['mode']} report", "", f"- Status: `{report['status']}`",
             f"- Cycles: `{report['cycles']}`", f"- Provider calls/failures: `{report['provider_calls']}/{report['provider_failures']}`",
             f"- Schema/policy rejections: `{report['schema_rejections']}/{report['policy_rejections']}`",
             f"- HOLD/candidate rates: `{report['hold_rate']:.4f}` / `{report['candidate_rate']:.4f}`",
             f"- Simulated entries/exits: `{report['simulated_entries']}/{report['simulated_exits']}`",
             f"- Net PnL after costs: `{report['net_pnl_after_costs']}`", "",
             "## Distributions", "", f"- Freshness: `{report['freshness_distribution']}`",
             f"- Spread: `{report['spread_distribution']}`", f"- Decision latency: `{report['decision_latency']}`", "",
             "## Safety", "", f"- Network calls: `{report['network_calls']}`",
             f"- Signed calls: `{report['signed_calls']}`", f"- Orders placed: `{report['orders_placed']}`",
             f"- Limitations: `{report.get('limitations', [])}`", ""]
    (reports_dir / "summary.md").write_text("\n".join(lines))
    return reports_dir / "summary.json", reports_dir / "summary.md"
