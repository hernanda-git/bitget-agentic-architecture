"""Venue/local state reconciliation and protection checks."""
from __future__ import annotations
from dataclasses import dataclass

from src.protection.models import ProtectionState


@dataclass(frozen=True)
class ReconcileResult:
    in_sync: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ProtectionReconcileResult:
    state: ProtectionState
    reasons: tuple[str, ...]

    @property
    def protected(self) -> bool:
        return self.state is ProtectionState.PROTECTED


def reconcile_positions(local: dict, venue: dict) -> ReconcileResult:
    reasons = []
    if set(local) != set(venue):
        reasons.append("POSITION_SYMBOL_DRIFT")
    for symbol in set(local) & set(venue):
        if local[symbol] != venue[symbol]:
            reasons.append(f"POSITION_DRIFT:{symbol}")
    return ReconcileResult(not reasons, tuple(reasons))


def reconcile_protection(*, intended: dict, venue: dict | None = None, bot_side: dict | None = None,
                         mark: float | None = None, liquidation_price: float | None = None,
                         side: str | None = None) -> ProtectionReconcileResult:
    venue = venue or {}
    bot_side = bot_side or {}
    reasons: list[str] = []
    sl, tp = intended.get("stop_loss"), intended.get("take_profit")
    venue_complete = venue.get("stop_loss") == sl and venue.get("take_profit") == tp and sl is not None and tp is not None
    bot_complete = (bot_side.get("armed") and bot_side.get("fresh") and
                    bot_side.get("stop_loss") == sl and bot_side.get("take_profit") == tp)
    if not venue_complete:
        reasons.append("VENUE_PROTECTION_MISSING")
    if not bot_complete and not venue_complete:
        reasons.append("BOT_MONITOR_NOT_VERIFIED")
    if liquidation_price is not None and sl is not None and side:
        wrong_side = (side.upper() == "LONG" and liquidation_price >= sl) or (side.upper() == "SHORT" and liquidation_price <= sl)
        if wrong_side:
            reasons.append("LIQUIDATION_GE_STOP" if side.upper() == "LONG" else "LIQUIDATION_LE_STOP")
    state = ProtectionState.PROTECTED if (venue_complete or bot_complete) and not any(r.startswith("LIQUIDATION_") for r in reasons) else ProtectionState.DEGRADED
    return ProtectionReconcileResult(state, tuple(reasons))


def verify_protection(position: dict) -> tuple[bool, str]:
    if not position.get("symbol"):
        return False, "NO_SYMBOL"
    if position.get("quantity", 0) <= 0:
        return False, "NO_OPEN_POSITION"
    if position.get("stop_loss") is None:
        return False, "STOP_LOSS_MISSING"
    if position.get("take_profit") is None:
        return False, "TAKE_PROFIT_MISSING"
    return True, "PROTECTED"
