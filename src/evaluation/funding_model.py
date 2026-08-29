"""Realistic Bitget funding-settlement accrual (pure, deterministic, offline).

Bitget USDT perpetuals settle funding every 8 hours at 00:00 / 08:00 / 16:00 UTC.
Because the Unix epoch (1970-01-01 00:00:00 UTC) is itself a settlement boundary,
every settlement timestamp is an exact multiple of ``8h`` in epoch milliseconds:
``k * 8h_ms`` for integer ``k``. This makes settlement membership a single modulus
check and makes the calendar trivially reproducible.

The previous cost model applied funding at every replay bar (a per-bar proxy), which
overstates funding by roughly the bar count for sub-8h holds and is not how the venue
bills. These helpers compute funding only at the real 8h settlement timestamps that
fall strictly inside a position's open interval, direction-aware, using the
per-settlement rate (already the 8h rate, e.g. 0.0001), never a per-bar rate.

No network, credentials, signed calls, or orders. Pure measurement + reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple

# 8 hours in milliseconds. Bitget USDT perpetuals settle funding at 00:00/08:00/16:00 UTC.
EIGHT_HOURS_MS = 8 * 3600 * 1000

# Direction the venue pays/receives for a given position side when the rate is positive.
# Longs pay a positive rate (shorts receive it); shorts pay a negative rate (longs receive).
_VALID_SIDES = ("BUY", "SELL")


@dataclass(frozen=True)
class FundingLeg:
    """One 8h settlement's funding accrual for a single position."""

    ts_ms: int
    rate: float
    mark: float
    paid: float
    received: float


def is_settlement_timestamp(ts_ms: int) -> bool:
    """True iff ``ts_ms`` is a Bitget funding-settlement boundary (multiple of 8h)."""
    return ts_ms % EIGHT_HOURS_MS == 0


def settlement_timestamps_in_range(start_ms: int, end_ms: int) -> List[int]:
    """All settlement timestamps strictly inside ``(start_ms, end_ms]``.

    Exclusive of ``start_ms`` (a position just opened at a settlement has not yet
    held through it) and inclusive of ``end_ms`` (a position closed exactly at a
    settlement has held through that settlement).
    """
    if end_ms <= start_ms:
        return []
    first = (start_ms // EIGHT_HOURS_MS + 1) * EIGHT_HOURS_MS
    out: List[int] = []
    ts = first
    while ts <= end_ms:
        out.append(ts)
        ts += EIGHT_HOURS_MS
    return out


def position_funding(
    side: str,
    quantity: float,
    entry_ts_ms: int,
    exit_ts_ms: int,
    mark_at: Callable[[int], float],
    rate_at: Callable[[int], float],
) -> Tuple[float, List[FundingLeg]]:
    """Net funding paid over a position open in ``(entry_ts_ms, exit_ts_ms]``.

    Funding is settled only at Bitget 8h boundaries strictly inside the open interval.
    ``rate_at`` returns the per-settlement rate at that boundary (already the 8h rate).
    ``mark_at`` returns the mark price at that boundary. Funding is direction-aware:
    a long pays when the rate is positive and receives when it is negative; a short is
    the mirror. Returns ``(net_paid, legs)`` where ``net_paid`` is paid minus received
    (positive = net cost to the position).
    """
    if side not in _VALID_SIDES:
        raise ValueError(f"funding side must be one of {_VALID_SIDES}, got {side!r}")
    if exit_ts_ms <= entry_ts_ms:
        return 0.0, []

    legs: List[FundingLeg] = []
    total_paid = 0.0
    total_received = 0.0
    for ts in settlement_timestamps_in_range(entry_ts_ms, exit_ts_ms):
        mark = mark_at(ts)
        rate = rate_at(ts)
        value = quantity * mark * rate
        if side == "BUY":
            paid = max(value, 0.0)
            received = max(-value, 0.0)
        else:  # SELL
            paid = max(-value, 0.0)
            received = max(value, 0.0)
        total_paid += paid
        total_received += received
        legs.append(FundingLeg(ts_ms=ts, rate=rate, mark=mark, paid=paid, received=received))
    return total_paid - total_received, legs


def reconcile_funding_legs(legs: List[FundingLeg]) -> float:
    """Return the net funding implied by a leg list (paid minus received).

    Used by tests and the ledger to prove the sum of per-settlement legs equals the
    reported position funding, closing the reconciliation loop on the realistic model.
    """
    return sum(leg.paid for leg in legs) - sum(leg.received for leg in legs)
