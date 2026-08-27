"""Fail-closed aggregation of per-symbol deterministic-baseline results.

The stored evidence base is growing (more symbols, deeper windows). A single
honest report must aggregate every per-symbol result WITHOUT laundering the
blocked baseline into a go-live claim.

Design (fail-closed by construction):

* ``selection_blocked`` is always carried through. Phase 6 (bounded LLM
  selection) is blocked in this repository, so ``aggregate_promotion_allowed``
  can only ever be True when selection is NOT blocked AND every symbol is
  positive AND every symbol is adequately sampled. With the repo's blocked
  baseline this is always False.
* The aggregate is self-validated by ``assert_truthful`` (recursive, per Phase
  18). A nested overclaim inside ANY per-symbol result is therefore refused
  before the aggregate is emitted. We additionally refuse to aggregate a
  per-symbol result that already contains an overclaim, so the guard runs on the
  inputs too, not only on the assembled output.
* No network, no credentials, no signed calls, no orders. This is aggregation of
  already-measured results only.

This module never changes the deterministic promotion gate and never selects.
"""
from __future__ import annotations

from typing import Any, Iterable

from src.evaluation.report_honesty import (
    ReportHonestyError,
    assert_truthful,
    find_overclaims,
)


def aggregate_symbol_results(
    results: Iterable[dict],
    *,
    selection_blocked: bool = True,
) -> dict:
    """Aggregate per-symbol deterministic-baseline results into one honest report.

    Parameters
    ----------
    results:
        Iterable of per-symbol result dicts. Each is expected to be honest
        already (e.g. produced by ``evaluate_real_history`` which itself calls
        ``assert_truthful``). The function refuses to aggregate any result that
        still contains an overclaim.
    selection_blocked:
        Whether Phase 6 selection is blocked. Always True in this repository.

    Returns
    -------
    dict
        The aggregate report. Always carries ``selection_blocked`` and is
        self-validated by ``assert_truthful`` before being returned.

    Raises
    ------
    ValueError
        When ``results`` is empty (nothing to aggregate).
    ReportHonestyError
        When any per-symbol result contains an overclaim, or when the assembled
        aggregate itself contains one (fail closed).
    """
    results = list(results)
    if not results:
        raise ValueError("no symbol results to aggregate")

    # Fail closed on any per-symbol overclaim. The recursive guard (Phase 18)
    # catches either a top-level or a nested forbidden key, so a smuggled
    # selection/winner claim inside a symbol sub-dict is refused too.
    for result in results:
        claims = find_overclaims(result)
        if claims:
            raise ReportHonestyError(
                "refusing to aggregate overclaiming symbol result: " + "; ".join(claims)
            )

    def _num(value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except (TypeError, ValueError):
            return default

    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(value if value is not None else default)
        except (TypeError, ValueError):
            return default

    overall_net = sum(_num(r.get("net_pnl")) for r in results)
    overall_trades = sum(_int(r.get("closed_trades")) for r in results)

    all_positive = all(_num(r.get("net_pnl")) > 0 for r in results)
    all_adequate = all(bool(r.get("adequate_sample", False)) for r in results)
    any_symbol_blocked = any(r.get("promotion_allowed") is False for r in results)

    # Promotion is allowed ONLY when nothing blocks it: selection not blocked,
    # no symbol blocked, every symbol positive, every symbol adequately sampled.
    aggregate_promotion_allowed = (
        (not selection_blocked)
        and (not any_symbol_blocked)
        and all_positive
        and all_adequate
    )

    aggregate = {
        "selection_blocked": selection_blocked,
        "symbols": [r.get("symbol") for r in results],
        "per_symbol": results,
        "overall_net_pnl": overall_net,
        "overall_closed_trades": overall_trades,
        "aggregate_promotion_allowed": bool(aggregate_promotion_allowed),
        "aggregate_promotion_reason": (
            "ALL_SYMBOLS_POSITIVE"
            if aggregate_promotion_allowed
            else "POSITIVE_EVIDENCE_REQUIRED"
        ),
        "robust_edge": False,
        "report_honest": True,
    }

    # Self-validate with the fail-closed, recursive truthfulness guard. If the
    # assembled aggregate somehow carries an overclaim (e.g. a key nested in a
    # per_symbol entry that find_overclaims on the input missed), this raises.
    assert_truthful(aggregate)
    return aggregate
