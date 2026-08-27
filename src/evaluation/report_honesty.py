"""Fail-closed truthfulness guard for evaluation / dashboard reports.

The deterministic promotion gate is ``NEGATIVE_NET_PNL`` and selection is always
blocked in this repository. A hand-maintained status ledger or a careless summary
can still OVERCLAIM: stamp ``promoted: true``, a ``verdict: PASS``,
``robust_edge: true`` without supporting evidence, or ``profitable: true`` while
net PnL is negative. Those claims would launder a blocked baseline into something
that looks ``go-live ready``.

This module is a fail-closed guard only:

* ``find_overclaims(report)`` returns a list of human-readable violation strings
  (empty when the report is honest).
* ``assert_truthful(report)`` raises ``ReportHonestyError`` (a ``ValueError``
  subclass) when any overclaim is present.

It never edits the report, never promotes, never selects, and never changes the
deterministic gate. It is compatible with ``selection_blocked`` being True.
"""
from __future__ import annotations

from typing import Any

# Keys that, when truthy, assert a selection / promotion / go-live decision.
# None of these are legitimate benign data keys in this repo.
FORBIDDEN_PROMOTION_KEYS = frozenset(
    {
        "promoted",
        "selected",
        "winner",
        "edge_confirmed",
        "go_live_ready",
        "phase6_promoted",
        "promoted_candidate",
    }
)

# Verdict strings that assert a positive gate while selection is blocked.
FORBIDDEN_VERDICTS = frozenset({"PASS", "POSITIVE", "APPROVED", "GO_LIVE", "WINNER"})

# Profitability-claim keys that contradict a non-positive net PnL.
PROFITABILITY_KEYS = ("profitable", "positive_expectancy")


class ReportHonestyError(ValueError):
    """Raised when an evaluation report contains an overclaim (fail-closed)."""


def _truthy(value: Any) -> bool:
    try:
        return bool(value)
    except Exception:
        return bool(value)


def find_overclaims(report: dict) -> list[str]:
    """Return the list of overclaim violations found in ``report``.

    An empty list means the report is honest (no overclaim). The function is
    pure and never mutates ``report``.
    """
    if not isinstance(report, dict):
        raise TypeError("report must be a dict")

    claims: list[str] = []

    # (a) forbidden promotion / selection keys, regardless of context, because
    #     no selection is ever permitted in this repo's blocked baseline.
    for key in FORBIDDEN_PROMOTION_KEYS:
        if key in report and _truthy(report[key]):
            claims.append(
                f"overclaim: '{key}' is truthy but Phase 6 selection is blocked"
            )

    # (b) forbidden verdict strings.
    verdict = report.get("verdict")
    if isinstance(verdict, str) and verdict.strip().upper() in FORBIDDEN_VERDICTS:
        claims.append(
            f"overclaim: verdict='{verdict}' asserts a positive gate while selection is blocked"
        )

    # (c) robust_edge requires supporting evidence (DSR positive + adequate
    #     sample + at least one Holm-surviving window).
    if report.get("robust_edge") is True:
        supported = (
            report.get("dsr_positive") is True
            and report.get("adequate_sample") is True
            and report.get("holm_surviving", 0) >= 1
        )
        if not supported:
            claims.append(
                "overclaim: robust_edge=True without dsr_positive + adequate_sample + holm_surviving>=1"
            )

    # (d) profitability claim contradicting a non-positive net PnL.
    for pk in PROFITABILITY_KEYS:
        if report.get(pk) is True:
            net = report.get("net_pnl", report.get("total_net_pnl"))
            if net is None:
                continue
            try:
                if float(net) <= 0:
                    claims.append(
                        f"overclaim: '{pk}'=True while net_pnl={net} <= 0"
                    )
            except (TypeError, ValueError):
                claims.append(
                    f"overclaim: '{pk}'=True but net_pnl is not a number ({net!r})"
                )

    # (e) explicit promotion_gate contradiction.
    pg = report.get("promotion_gate")
    if pg is not None and str(pg).strip().upper() in {"POSITIVE", "PASS", "APPROVED"}:
        if report.get("selection_blocked") is True:
            claims.append(
                f"overclaim: promotion_gate='{pg}' while selection_blocked=True"
            )

    return claims


def assert_truthful(report: dict) -> None:
    """Raise ``ReportHonestyError`` if ``report`` contains any overclaim.

    Fail-closed: any detected overclaim aborts the caller. Callers (report
    writers, dashboard projections) must not emit the report when this raises.
    """
    claims = find_overclaims(report)
    if claims:
        raise ReportHonestyError("; ".join(claims))
