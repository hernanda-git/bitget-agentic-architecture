from src.reconcile.engine import reconcile_protection
from src.protection.models import ProtectionState


def test_missing_venue_levels_are_not_protected_without_fresh_armed_monitor():
    result = reconcile_protection(
        intended={"stop_loss": 95, "take_profit": 110},
        venue={"stop_loss": None, "take_profit": None},
        bot_side={"armed": False, "fresh": False},
        mark=100,
        liquidation_price=80,
        side="LONG",
    )
    assert result.state is ProtectionState.DEGRADED
    assert "VENUE_PROTECTION_MISSING" in result.reasons


def test_fresh_bot_monitor_can_protect_missing_venue_levels():
    result = reconcile_protection(
        intended={"stop_loss": 95, "take_profit": 110},
        venue={},
        bot_side={"armed": True, "fresh": True, "stop_loss": 95, "take_profit": 110},
        mark=100,
        liquidation_price=80,
        side="LONG",
    )
    assert result.state is ProtectionState.PROTECTED


def test_liquidation_on_wrong_side_degrades_protection():
    result = reconcile_protection(
        intended={"stop_loss": 95, "take_profit": 110},
        venue={"stop_loss": 95, "take_profit": 110},
        mark=100,
        liquidation_price=100,
        side="LONG",
    )
    assert result.state is ProtectionState.DEGRADED
    assert "LIQUIDATION_GE_STOP" in result.reasons
