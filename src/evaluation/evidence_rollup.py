"""Fail-closed rollup of per-symbol request evidence for honest multi-symbol reporting.

When several per-symbol deterministic-baseline reports are folded into one
multi-symbol aggregate, the combined report must transparently disclose the
TOTAL network activity that produced the evidence, and must prove the run never
signed an exchange call or used credentials. Every entry point is fail-closed:
any signed call or credential use anywhere in the evidence base raises, and an
empty evidence base is rejected rather than invented as zeros.
"""
from __future__ import annotations

from typing import Iterable

_REQUIRED_KEYS = (
    "requests", "successes", "failures", "rate_limits", "retries",
    "signed_calls", "credentials_used",
)


def roll_up_request_evidence(evidences: Iterable[dict]) -> dict:
    """Roll the per-symbol ``request_evidence`` blocks into one fail-closed summary.

    Sums the network counters across every symbol, asserts the aggregate made
    ZERO signed calls and used ZERO credentials (constitutional invariants for
    this repo), and reports ``all_unauthenticated``. Failures:

    * empty evidence base -> ``ValueError`` (nothing to roll up)
    * any ``signed_calls > 0`` -> ``ValueError`` (must never sign)
    * any ``credentials_used is True`` -> ``ValueError`` (must never use secrets)

    Pure measurement. Never touches the deterministic promotion gate.
    """
    items = tuple(evidences)
    if not items:
        raise ValueError("roll_up_request_evidence requires at least one evidence block")

    numeric_keys = tuple(k for k in _REQUIRED_KEYS if k != "credentials_used")
    totals = {k: 0 for k in numeric_keys}
    credentials_used = False
    symbols = 0
    for ev in items:
        if not isinstance(ev, dict):
            raise ValueError("each request_evidence block must be a mapping")
        for key in numeric_keys:
            if key not in ev:
                raise ValueError(f"request_evidence missing key: {key}")
            val = ev[key]
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ValueError(f"request_evidence.{key} must be numeric")
            totals[key] += val
        used = ev.get("credentials_used", False)
        if not isinstance(used, bool):
            raise ValueError("request_evidence.credentials_used must be a bool")
        if used:
            # The repo must never use secrets. One tainted report taints the
            # whole evidence base; refuse rather than aggregate it.
            raise ValueError("credentials were used in a report; rollup refused")
        credentials_used = credentials_used or used
        symbols += 1

    # The repo must never sign an exchange call. A single signed call anywhere
    # taints the whole evidence base; refuse rather than aggregate it.
    if totals["signed_calls"] != 0:
        raise ValueError("signed_calls detected in evidence base; rollup refused")

    return {
        "symbols": symbols,
        "requests": totals["requests"],
        "successes": totals["successes"],
        "failures": totals["failures"],
        "rate_limits": totals["rate_limits"],
        "retries": totals["retries"],
        "signed_calls": totals["signed_calls"],
        "credentials_used": credentials_used,
        "all_unauthenticated": totals["signed_calls"] == 0 and not credentials_used,
    }
