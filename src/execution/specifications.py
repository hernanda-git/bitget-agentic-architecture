"""Immutable venue constraints used by the paper exchange."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

class VenueRuleError(ValueError): pass

def _multiple(value: float, step: float) -> bool:
    q = Decimal(str(value)) / Decimal(str(step))
    return q == q.to_integral_value()

@dataclass(frozen=True)
class FeeSchedule:
    maker_bps: float = 2.0
    taker_bps: float = 5.0

@dataclass(frozen=True)
class FundingSchedule:
    rate_per_event: float = 0.0

@dataclass(frozen=True)
class VenueSpecification:
    price_tick: float
    quantity_step: float
    minimum_quantity: float
    minimum_notional: float
    contract_multiplier: float
    fee_schedule: FeeSchedule
    funding_schedule: FundingSchedule
    max_leverage: float
    allowed_margin_modes: frozenset[str]

    def validate_order(self, *, symbol: str, quantity: float, price: float, leverage: float = 1, margin_mode: str = "isolated") -> None:
        if not symbol: raise VenueRuleError("symbol required")
        if quantity <= 0 or not _multiple(quantity, self.quantity_step): raise VenueRuleError("quantity step")
        if quantity < self.minimum_quantity: raise VenueRuleError("minimum quantity")
        if price <= 0 or not _multiple(price, self.price_tick): raise VenueRuleError("price tick")
        if quantity * price * self.contract_multiplier < self.minimum_notional: raise VenueRuleError("minimum notional")
        if leverage <= 0 or leverage > self.max_leverage: raise VenueRuleError("max leverage")
        if margin_mode not in self.allowed_margin_modes: raise VenueRuleError("margin mode")
