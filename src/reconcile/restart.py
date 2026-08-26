"""Fail-closed restart reconciliation before a paper entry is permitted."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.reconcile.engine import reconcile_positions


def recover_before_new_entries(local: Mapping[str, Any], venue: Mapping[str, Any], *,
                               interrupted_cycles: Sequence[str] = (),
                               kill_switch: bool = False,
                               provider_available: bool = True) -> dict[str, Any]:
    """Reconcile durable/local state first and return an explicit gate decision.

    This function is deliberately side-effect free so restart tests can use bounded
    fakes. Any drift, kill switch, or unavailable provider parks new entries.
    Interrupted cycles are recoverable until their next lifecycle pass.
    """
    if kill_switch:
        return {"status": "PARKED", "reason": "KILL_SWITCH_ACTIVE"}
    if not provider_available:
        return {"status": "PARKED", "reason": "PROVIDER_OUTAGE"}
    reconciliation = reconcile_positions(dict(local), dict(venue))
    if not reconciliation.in_sync:
        return {"status": "PARKED", "reason": "RECONCILIATION_DRIFT", "details": reconciliation.reasons}
    result: dict[str, Any] = {"status": "READY"}
    if interrupted_cycles:
        result["interrupted_cycles"] = {cycle_id: "RECOVERABLE" for cycle_id in interrupted_cycles}
    return result
