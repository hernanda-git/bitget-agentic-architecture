"""Layer 7 protection read-back must reject a stop on the WRONG side of mark.

A protective stop must sit on the adverse side of the current mark for the position
side: a LONG stop_loss must be strictly BELOW mark, a SHORT stop_loss strictly ABOVE
mark. If the venue echoes back a stop that equals or crosses mark (a misconfigured or
garbled stop), the position is effectively UNPROTECTED against adverse moves yet the
read-back would otherwise report PROTECTED. This is the "accepted-but-dropped /
wrong-side protection" failure mode from the agentic-architecture threat model.

No signed calls, no credentials, no orders. Pure offline measurement over fakes.
"""
import pytest

from src.reconcile.engine import reconcile_protection
from src.protection.models import ProtectionState
from src.protection.supervisor import ProtectionSupervisor
from src.protection.models import InMemoryProtectionStore


# --- reconcile_protection (canonical venue read-back check) ---

def test_reconcile_protection_degrades_long_stop_above_mark():
    """A LONG whose stop is ABOVE the mark is not protective -> DEGRADED."""
    result = reconcile_protection(
        intended={"stop_loss": 105, "take_profit": 110},
        venue={"stop_loss": 105, "take_profit": 110},
        mark=100, side="LONG",
    )
    assert result.state is ProtectionState.DEGRADED
    assert "WRONG_SIDE_STOP" in result.reasons


def test_reconcile_protection_degrades_short_stop_below_mark():
    """A SHORT whose stop is BELOW the mark is not protective -> DEGRADED."""
    result = reconcile_protection(
        intended={"stop_loss": 95, "take_profit": 90},
        venue={"stop_loss": 95, "take_profit": 90},
        mark=100, side="SHORT",
    )
    assert result.state is ProtectionState.DEGRADED
    assert "WRONG_SIDE_STOP" in result.reasons


def test_reconcile_protection_degrades_stop_at_mark():
    """A stop exactly AT mark gives no protection -> DEGRADED (edge boundary)."""
    result = reconcile_protection(
        intended={"stop_loss": 100, "take_profit": 110},
        venue={"stop_loss": 100, "take_profit": 110},
        mark=100, side="LONG",
    )
    assert result.state is ProtectionState.DEGRADED
    assert "WRONG_SIDE_STOP" in result.reasons


def test_reconcile_protection_allows_protective_long_stop():
    """A genuine LONG stop below mark is PROTECTED (positive control)."""
    result = reconcile_protection(
        intended={"stop_loss": 95, "take_profit": 110},
        venue={"stop_loss": 95, "take_profit": 110},
        mark=100, side="LONG",
    )
    assert result.state is ProtectionState.PROTECTED
    assert not any("WRONG_SIDE_STOP" in r for r in result.reasons)


def test_reconcile_protection_allows_protective_short_stop():
    """A genuine SHORT stop above mark is PROTECTED (positive control)."""
    result = reconcile_protection(
        intended={"stop_loss": 105, "take_profit": 90},
        venue={"stop_loss": 105, "take_profit": 90},
        mark=100, side="SHORT",
    )
    assert result.state is ProtectionState.PROTECTED
    assert not any("WRONG_SIDE_STOP" in r for r in result.reasons)


# --- ProtectionSupervisor.verify (live path, must delegate to canonical check) ---

def test_supervisor_verify_degrades_wrong_side_stop():
    """The active supervisor path must also reject a wrong-side stop (via delegation)."""
    supervisor = ProtectionSupervisor(InMemoryProtectionStore())
    # Register a garbled LONG whose intended stop is ABOVE entry/mark.
    supervisor.register_position("BTCUSDT", "LONG", 1, 105, 110)
    record = supervisor.verify("BTCUSDT", venue={"stop_loss": 105, "take_profit": 110}, mark=100)
    assert record.state is ProtectionState.DEGRADED
    assert "WRONG_SIDE_STOP" in record.to_dict().get("reasons", ())
    assert supervisor.entries_parked
