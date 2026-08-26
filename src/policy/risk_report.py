"""Effective risk reporting based on venue-adjusted sizing."""
from __future__ import annotations

from dataclasses import dataclass

from src.policy.sizing import SizingResult


@dataclass(frozen=True)
class EffectiveRiskReport:
    requested_risk_usd: float
    actual_quantity: float
    actual_notional_usd: float
    actual_stop_distance_usd: float
    realized_risk_usd: float
    risk_percent_equity: float
    risk_vs_daily_cap: float
    implied_leverage: float
    minimum_notional_distortion: bool

    @property
    def effective_risk_usd(self) -> float:
        return self.realized_risk_usd

    @property
    def actual_risk_percent_equity(self) -> float:
        return self.risk_percent_equity

    # Explicit domain names make it impossible to confuse configured/requested
    # risk with venue-constrained, executable dimensions.
    @property
    def venue_constrained_quantity(self) -> float:
        return self.actual_quantity

    @property
    def actual_notional(self) -> float:
        return self.actual_notional_usd

    @property
    def stop_distance(self) -> float:
        return self.actual_stop_distance_usd

    @property
    def realized_risk(self) -> float:
        return self.realized_risk_usd

    @property
    def leverage(self) -> float:
        return self.implied_leverage


def build_risk_report(*, sizing: SizingResult, equity_usd: float,
                      daily_loss_cap_usd: float, entry: float,
                      stop_loss: float, margin_used_usd: float) -> EffectiveRiskReport:
    if equity_usd <= 0 or daily_loss_cap_usd <= 0 or entry <= 0 or margin_used_usd <= 0:
        raise ValueError("equity, daily cap, entry, and margin must be positive")
    distance = abs(entry - stop_loss)
    return EffectiveRiskReport(
        requested_risk_usd=sizing.requested_risk_usd,
        actual_quantity=sizing.quantity,
        actual_notional_usd=sizing.notional_usd,
        actual_stop_distance_usd=distance,
        realized_risk_usd=sizing.effective_risk_usd,
        risk_percent_equity=sizing.effective_risk_usd / equity_usd * 100,
        risk_vs_daily_cap=sizing.effective_risk_usd / daily_loss_cap_usd,
        implied_leverage=sizing.notional_usd / margin_used_usd,
        minimum_notional_distortion=sizing.raised_to_minimum,
    )


# Short alias for integrations.
risk_report = build_risk_report
