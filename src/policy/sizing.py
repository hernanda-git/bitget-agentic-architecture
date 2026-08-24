"""Deterministic risk sizing. The provider cannot choose final quantity."""
from __future__ import annotations

import math
from dataclasses import dataclass


class SizingError(ValueError):
    pass


@dataclass(frozen=True)
class SizingResult:
    quantity: float
    notional_usd: float
    effective_risk_usd: float
    requested_risk_usd: float
    capped_by_max: bool
    raised_to_minimum: bool


def _floor_step(value: float, step: float) -> float:
    return math.floor((value + 1e-12) / step) * step


def size_for_risk(*, side: str, entry: float, stop_loss: float, requested_risk_usd: float,
                  min_notional_usd: float, max_notional_usd: float, quantity_step: float = 1.0) -> SizingResult:
    if side not in {"BUY", "SELL"}:
        raise SizingError("invalid side")
    if entry <= 0 or stop_loss <= 0 or requested_risk_usd <= 0:
        raise SizingError("positive entry, stop, and risk are required")
    if side == "BUY" and stop_loss >= entry:
        raise SizingError("long stop must be below entry")
    if side == "SELL" and stop_loss <= entry:
        raise SizingError("short stop must be above entry")
    if min_notional_usd <= 0 or max_notional_usd < min_notional_usd or quantity_step <= 0:
        raise SizingError("invalid venue limits")
    risk_per_unit = abs(entry - stop_loss)
    requested_qty = requested_risk_usd / risk_per_unit
    requested_notional = requested_qty * entry
    capped = requested_notional > max_notional_usd
    raised_to_minimum = requested_notional < min_notional_usd
    target_notional = min(max(requested_notional, min_notional_usd), max_notional_usd)
    quantity = _floor_step(target_notional / entry, quantity_step)
    if quantity <= 0:
        raise SizingError("venue quantity step leaves no valid quantity")
    notional = quantity * entry
    if notional < min_notional_usd:
        raise SizingError("quantity step cannot satisfy minimum notional")
    return SizingResult(quantity, notional, quantity * risk_per_unit, requested_risk_usd,
                        capped, raised_to_minimum)
