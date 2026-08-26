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
    stop_distance_usd: float = 0.0
    contract_multiplier: float = 1.0

    @property
    def venue_constrained_quantity(self) -> float:
        return self.quantity

    @property
    def actual_notional(self) -> float:
        return self.notional_usd

    @property
    def realized_risk_usd(self) -> float:
        return self.effective_risk_usd


def _finite_positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise SizingError(f"{name} must be finite and positive")


def _floor_step(value: float, step: float) -> float:
    return math.floor((value + 1e-12) / step) * step


def size_for_risk(*, side: str, entry: float, stop_loss: float, requested_risk_usd: float,
                  min_notional_usd: float, max_notional_usd: float, quantity_step: float = 1.0,
                  contract_multiplier: float = 1.0, available_equity_usd: float | None = None,
                  existing_gross_notional_usd: float = 0.0,
                  max_total_notional_usd: float | None = None,
                  provider_quantity: float | None = None) -> SizingResult:
    if provider_quantity is not None:
        raise SizingError("provider quantity is not executable")
    if side not in {"BUY", "SELL"}:
        raise SizingError("invalid side")
    for value, name in ((entry, "entry"), (stop_loss, "stop"),
                        (requested_risk_usd, "risk"), (min_notional_usd, "minimum notional"),
                        (max_notional_usd, "maximum notional"), (quantity_step, "quantity step"),
                        (contract_multiplier, "contract multiplier")):
        _finite_positive(value, name)
    if available_equity_usd is not None:
        _finite_positive(available_equity_usd, "available equity")
    if not math.isfinite(existing_gross_notional_usd) or existing_gross_notional_usd < 0:
        raise SizingError("existing exposure must be finite and non-negative")
    if max_notional_usd < min_notional_usd:
        raise SizingError("maximum notional must cover minimum notional")
    if max_total_notional_usd is not None:
        _finite_positive(max_total_notional_usd, "maximum total notional")
    if side == "BUY" and stop_loss >= entry:
        raise SizingError("long stop must be below entry")
    if side == "SELL" and stop_loss <= entry:
        raise SizingError("short stop must be above entry")
    distance = abs(entry - stop_loss)
    risk_per_unit = distance * contract_multiplier
    requested_qty = requested_risk_usd / risk_per_unit
    requested_notional = requested_qty * entry * contract_multiplier
    exposure_room = max_notional_usd
    if max_total_notional_usd is not None:
        exposure_room = min(exposure_room, max_total_notional_usd - existing_gross_notional_usd)
    if available_equity_usd is not None:
        exposure_room = min(exposure_room, available_equity_usd)
    if exposure_room <= 0:
        raise SizingError("portfolio exposure or available equity exhausted")
    capped = requested_notional > exposure_room
    raised_to_minimum = requested_notional < min_notional_usd
    target_notional = min(max(requested_notional, min_notional_usd), exposure_room)
    quantity = _floor_step(target_notional / (entry * contract_multiplier), quantity_step)
    if quantity <= 0:
        raise SizingError("venue quantity step leaves no valid quantity")
    notional = quantity * entry * contract_multiplier
    if notional < min_notional_usd:
        raise SizingError("quantity step cannot satisfy minimum notional")
    if notional > exposure_room + 1e-9:
        raise SizingError("quantity step exceeds portfolio exposure")
    return SizingResult(quantity, notional, quantity * risk_per_unit, requested_risk_usd,
                        capped, raised_to_minimum, distance, contract_multiplier)
