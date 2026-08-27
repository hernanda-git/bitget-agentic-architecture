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

# Hard cap on recursion depth. A report is a shallow, structured summary; no
# legitimate report nests dozens of levels deep. The cap guarantees the scan
# always terminates even on a pathological / adversarial input.
MAX_SCAN_DEPTH = 50

# Promotion / selection keys that are unambiguous overclaims WHENEVER they
# appear, including nested. ``selected`` is deliberately EXCLUDED here: it is
# checked only at the top level, because legitimate evaluation dicts sometimes
# carry sub-keys such as ``selected_feature`` / ``selected_strategy`` that must
# not be mistaken for a selection/overclaim signal.
NESTED_FORBIDDEN_PROMOTION_KEYS = frozenset(
    {
        "promoted",
        "winner",
        "edge_confirmed",
        "go_live_ready",
        "phase6_promoted",
        "promoted_candidate",
    }
)


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

    The scan recurses into nested dicts and lists so a forbidden
    promotion/selection/verdict/profitability key buried inside an unrelated
    sub-dict is still caught (this closed the Phase 17 limitation that the
    guard only inspected the top level). A depth cap (``MAX_SCAN_DEPTH``)
    guarantees termination on pathological structures.
    """
    if not isinstance(report, dict):
        raise TypeError("report must be a dict")

    claims: list[str] = []
    selection_blocked = report.get("selection_blocked") is True

    # Top-level-only check for ``selected``. It is intentionally NOT part of the
    # nested recursion set, because legitimate evaluation dicts can carry
    # sub-keys such as ``selected_feature`` / ``selected_strategy`` that must not
    # be mistaken for a selection overclaim. Only a top-level ``selected`` is an
    # overclaim signal.
    if "selected" in report and _truthy(report["selected"]):
        claims.append(
            "overclaim: 'selected' is truthy but Phase 6 selection is blocked"
        )

    # Recurse every node for the unambiguous nested overclaim signals.
    _scan_node(report, claims, depth=0, selection_blocked=selection_blocked)

    # (c) robust_edge cross-check stays TOP LEVEL only: it needs the top-level
    #     sibling evidence (dsr_positive / adequate_sample / holm_surviving),
    #     which a nested dict would not carry.
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

    return claims


def _scan_node(node: Any, claims: list[str], depth: int, selection_blocked: bool) -> None:
    """Recursively scan ``node`` for nested overclaim signals.

    Applies rules (a) nested forbidden promotion keys, (b) forbidden verdict
    strings, (d) nested profitability contradictions, and (e) nested
    promotion_gate contradictions (using the top-level ``selection_blocked``
    fact). Descends into dict values and list/tuple/set elements, bounded by
    ``MAX_SCAN_DEPTH`` to guarantee termination.
    """
    if depth > MAX_SCAN_DEPTH:
        return
    if isinstance(node, dict):
        # (a) unambiguous nested forbidden promotion / selection keys.
        for key in NESTED_FORBIDDEN_PROMOTION_KEYS:
            if key in node and _truthy(node[key]):
                claims.append(
                    f"overclaim[nested]: '{key}' is truthy but Phase 6 selection is blocked"
                )

        # (b) forbidden verdict strings at any level.
        verdict = node.get("verdict")
        if isinstance(verdict, str) and verdict.strip().upper() in FORBIDDEN_VERDICTS:
            claims.append(
                f"overclaim[nested]: verdict='{verdict}' asserts a positive gate while selection is blocked"
            )

        # (d) nested profitability contradiction (uses this node's own net_pnl
        #     if present; otherwise the check is skipped to avoid false claims
        #     about an unrelated parent-level figure).
        for pk in PROFITABILITY_KEYS:
            if node.get(pk) is True:
                net = node.get("net_pnl", node.get("total_net_pnl"))
                if net is None:
                    continue
                try:
                    if float(net) <= 0:
                        claims.append(
                            f"overclaim[nested]: '{pk}'=True while net_pnl={net} <= 0"
                        )
                except (TypeError, ValueError):
                    claims.append(
                        f"overclaim[nested]: '{pk}'=True but net_pnl is not a number ({net!r})"
                    )

        # (e) nested promotion_gate contradiction (uses top-level selection_blocked).
        pg = node.get("promotion_gate")
        if pg is not None and str(pg).strip().upper() in {"POSITIVE", "PASS", "APPROVED"}:
            if selection_blocked:
                claims.append(
                    f"overclaim[nested]: promotion_gate='{pg}' while selection_blocked=True"
                )

        for value in node.values():
            _scan_node(value, claims, depth + 1, selection_blocked)
    elif isinstance(node, (list, tuple, set)):
        for value in node:
            _scan_node(value, claims, depth + 1, selection_blocked)


def assert_truthful(report: dict) -> None:
    """Raise ``ReportHonestyError`` if ``report`` contains any overclaim.

    Fail-closed: any detected overclaim aborts the caller. Callers (report
    writers, dashboard projections) must not emit the report when this raises.
    """
    claims = find_overclaims(report)
    if claims:
        raise ReportHonestyError("; ".join(claims))
