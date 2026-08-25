from src.protection.models import ProtectionState, InMemoryProtectionStore
from src.protection.supervisor import ProtectionSupervisor


def test_new_position_starts_pending_and_missing_levels_degrade():
    supervisor = ProtectionSupervisor(InMemoryProtectionStore())
    record = supervisor.register_position("BTCUSDT", "LONG", 1, 95, 110)
    assert record.state is ProtectionState.PENDING
    assert supervisor.verify("BTCUSDT", venue={"stop_loss": None, "take_profit": None}).state is ProtectionState.DEGRADED
    assert supervisor.entries_parked


def test_missing_intended_levels_are_never_protected():
    supervisor = ProtectionSupervisor(InMemoryProtectionStore())
    supervisor.register_position("BTCUSDT", "LONG", 1, None, None)
    assert supervisor.verify("BTCUSDT", venue={"stop_loss": None, "take_profit": None}).state is ProtectionState.DEGRADED


def test_fresh_bot_monitor_cannot_protect_without_intended_levels():
    supervisor = ProtectionSupervisor(InMemoryProtectionStore())
    supervisor.register_position("BTCUSDT", "LONG", 1, None, None)

    record = supervisor.verify(
        "BTCUSDT",
        venue={"stop_loss": None, "take_profit": None},
        bot_monitor_armed=True,
        bot_monitor_fresh=True,
    )

    assert record.state is ProtectionState.DEGRADED
    assert supervisor.entries_parked


def test_only_verified_venue_or_fresh_bot_monitor_can_protect():
    supervisor = ProtectionSupervisor(InMemoryProtectionStore())
    supervisor.register_position("BTCUSDT", "LONG", 1, 95, 110)
    assert supervisor.verify("BTCUSDT", venue={"stop_loss": 95, "take_profit": 110}).state is ProtectionState.PROTECTED

    supervisor.register_position("ETHUSDT", "LONG", 1, 90, 120)
    assert supervisor.verify("ETHUSDT", venue={"stop_loss": None, "take_profit": None}, bot_monitor_armed=True, bot_monitor_fresh=True).state is ProtectionState.PROTECTED


def test_unknown_and_degraded_park_entries_but_closed_does_not():
    supervisor = ProtectionSupervisor(InMemoryProtectionStore())
    supervisor.register_position("BTCUSDT", "LONG", 1, 95, 110)
    assert supervisor.mark_unknown("BTCUSDT").state is ProtectionState.UNKNOWN
    assert supervisor.entries_parked
    assert supervisor.close("BTCUSDT").state is ProtectionState.CLOSED
    assert not supervisor.entries_parked


def test_supervisor_restores_state_after_restart():
    store = InMemoryProtectionStore()
    first = ProtectionSupervisor(store)
    first.register_position("BTCUSDT", "SHORT", 2, 105, 90)
    first.verify("BTCUSDT", venue={"stop_loss": None, "take_profit": None}, bot_monitor_armed=True, bot_monitor_fresh=True)
    restored = ProtectionSupervisor(store)
    assert restored.get("BTCUSDT").state is ProtectionState.PROTECTED
    assert restored.get("BTCUSDT").stop_loss == 105
