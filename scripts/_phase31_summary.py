"""Summarize the phase-31 per-symbol baseline reports + fail-closed evidence rollup.

Reads every ``*-1m.json`` deterministic-baseline report in ``reports/phase-31``,
prints a per-symbol table, and rolls the per-symbol ``request_evidence`` blocks
through the fail-closed ``roll_up_request_evidence`` guard. Writes both to
``reports/phase-31/evidence_summary.json`` for the phase report.

No network, no credentials, no signed calls. Reads report files only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.evidence_rollup import roll_up_request_evidence

REPORTS_DIR = ROOT / "reports" / "phase-31"


def _main() -> int:
    files = sorted(REPORTS_DIR.glob("*-1m.json"))
    rows = []
    evidences = []
    for f in files:
        payload = json.loads(f.read_text())
        baseline = payload.get("baseline", {})
        wfr = payload.get("walk_forward_robustness", {}) or {}
        ev = payload.get("request_evidence", {}) or {}
        rows.append({
            "symbol": payload.get("symbol"),
            "candles": payload.get("candles"),
            "fetched_at_ms": payload.get("fetched_at_ms"),
            "closed_trades": baseline.get("closed_trades"),
            "gross_pnl": baseline.get("gross_pnl"),
            "fees": baseline.get("fees"),
            "spread": baseline.get("spread"),
            "slippage": baseline.get("slippage"),
            "funding": baseline.get("funding"),
            "net_pnl": baseline.get("net_pnl"),
            "promotion_allowed": baseline.get("promotion_allowed"),
            "promotion_reason": baseline.get("promotion_reason"),
            "adequate_sample": bool(wfr.get("adequate_sample", False)),
            "wf_windows": len(payload.get("walk_forward", []) or []),
            "requests": ev.get("requests"),
            "successes": ev.get("successes"),
            "failures": ev.get("failures"),
            "rate_limits": ev.get("rate_limits"),
            "signed_calls": ev.get("signed_calls"),
            "credentials_used": ev.get("credentials_used"),
        })
        evidences.append(ev)

    rollup = roll_up_request_evidence(evidences)
    out = {"rows": rows, "evidence_rollup": rollup}
    (REPORTS_DIR / "evidence_summary.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, default=str) + "\n")

    print(f"symbols={len(rows)}")
    for r in rows:
        print(f"  {r['symbol']:10s} candles={r['candles']} trades={r['closed_trades']:>4} "
              f"gross={r['gross_pnl']:>10.4f} net={r['net_pnl']:>10.4f} "
              f"promo={r['promotion_allowed']} reason={r['promotion_reason']} "
              f"wf_windows={r['wf_windows']} adequate={r['adequate_sample']}")
    print("EVIDENCE ROLLUP:", json.dumps(rollup, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
