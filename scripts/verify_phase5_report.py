#!/usr/bin/env python3
"""Fail-closed consistency check for the checked-in Phase 5 evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


_NUMERIC_FIELDS = (
    "snapshots",
    "network_calls",
    "signed_calls",
    "orders",
    "closed_trades",
    "open_positions",
    "end_of_replay_closes",
    "protection_attachments",
    "reconciliation_checks",
    "gross_pnl",
    "fees",
    "spread",
    "slippage",
    "funding",
    "net_pnl",
    "promotion_allowed",
    "promotion_reason",
    "replay_hash",
)


def _load(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"unable to load {path}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{path} must contain a JSON object")
        return None
    return value


def validate_phase5_report(root: Path) -> list[str]:
    """Return all inconsistencies between Phase 5 JSON and Markdown artifacts."""
    root = Path(root)
    report_dir = root / "reports" / "phase-5"
    errors: list[str] = []
    baseline = _load(report_dir / "baseline.json", errors)
    summary = _load(report_dir / "summary.json", errors)
    try:
        markdown = (report_dir / "summary.md").read_text()
    except OSError as exc:
        errors.append(f"unable to load {report_dir / 'summary.md'}: {exc}")
        markdown = ""

    if baseline is None or summary is None:
        return errors

    # The compact phase summary intentionally has a different schema. Compare
    # only fields it publishes, while requiring the detailed baseline to drive
    # all numerical Markdown claims below.
    for field in _NUMERIC_FIELDS:
        if field in summary and baseline.get(field) != summary.get(field):
            errors.append(
                f"summary.json drift for {field}: "
                f"baseline={baseline.get(field)!r}, summary={summary.get(field)!r}"
            )
    for field in ("walk_forward_evaluation", "cost_stress"):
        if field not in summary:
            continue
        summary_rows = summary[field]
        baseline_rows = baseline.get(field)
        if not isinstance(summary_rows, list) or not isinstance(baseline_rows, list) or len(summary_rows) != len(baseline_rows):
            errors.append(f"summary.json drift for {field}")
            continue
        for index, summary_row in enumerate(summary_rows):
            baseline_row = baseline_rows[index]
            if not isinstance(summary_row, dict) or not isinstance(baseline_row, dict):
                errors.append(f"summary.json drift for {field}[{index}]")
                continue
            for key, value in summary_row.items():
                if baseline_row.get(key) != value:
                    errors.append(f"summary.json drift for {field}[{index}].{key}")

    compact_fields = {
        "walk_forward_protection_attachments": "protection_attachments",
        "walk_forward_reconciliation_checks": "reconciliation_checks",
    }
    for compact_field, row_field in compact_fields.items():
        if compact_field not in summary:
            continue
        expected = [
            row.get(row_field)
            for row in baseline.get("walk_forward_evaluation", [])
        ]
        if summary[compact_field] != expected:
            errors.append(f"summary.json drift for {compact_field}")

    markdown_expectations = {
        "network calls": f"- Trading-runtime network calls: `{baseline['network_calls']}`",
        "signed calls": f"- Signed calls: `{baseline['signed_calls']}`",
        "orders": f"- Runner-submitted paper orders: `{baseline['orders']}`",
        "open positions": f"- Open positions at replay end: `{baseline['open_positions']}`",
        "closed trades": f"- Closed trades: `{baseline['closed_trades']}`",
        "end-of-replay closes": f"- End-of-replay closes: `{baseline['end_of_replay_closes']}`",
        "protection attachments": f"- Protection attachments: `{baseline['protection_attachments']}`",
        "reconciliation checks": f"- Reconciliation checks: `{baseline['reconciliation_checks']}`",
        "gross PnL": f"- Gross PnL: `{baseline['gross_pnl']}`",
        "fees": f"- Fees: `{baseline['fees']}`",
        "spread": f"- Spread: `{baseline['spread']}`",
        "slippage": f"- Simulated slippage: `{baseline['slippage']}`",
        "funding": f"- Funding: `{baseline['funding']}`",
        "net PnL": f"- Net PnL: `{baseline['net_pnl']}`",
        "promotion reason": f"- Promotion reason: `{baseline['promotion_reason']}`",
        "replay hash": f"- Replay hash: `{baseline['replay_hash']}`",
    }
    walk_forward = baseline.get("walk_forward_evaluation", [])
    if len(walk_forward) == 1:
        row = walk_forward[0]
        markdown_expectations["walk-forward net PnL"] = (
            f"- Walk-forward net PnL was `{row['net_pnl']}` "
            f"for the complete window `[{row['test_start']},{row['test_end']}]`."
        )
    else:
        errors.append("baseline walk_forward_evaluation must contain exactly one complete window")

    for label, expected in markdown_expectations.items():
        if expected not in markdown:
            errors.append(f"summary.md stale or missing {label}: {expected}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    errors = validate_phase5_report(args.root)
    print(json.dumps({"ok": not errors, "errors": errors}, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
