from src.protection.mark_monitor import MarkMonitor
from src.protection.models import InMemoryProtectionStore, ProtectionState


def test_monitor_handles_long_breach_once_and_preserves_levels():
    closes = []
    monitor = MarkMonitor(InMemoryProtectionStore(), close_position=lambda symbol: closes.append(symbol), stale_after=5, clock=lambda: 100)
    monitor.arm("BTCUSDT", "LONG", 1, 95, 110, timestamp=99)
    events = monitor.on_mark("BTCUSDT", 95, timestamp=100)
    assert events[0].kind == "EMERGENCY_EXIT_PENDING"
    assert events[1].kind == "CLOSED"
    assert closes == ["BTCUSDT"]
    assert monitor.on_mark("BTCUSDT", 93, timestamp=100) == []
    armed = monitor.get("BTCUSDT")
    assert armed.stop_loss == 95 and armed.take_profit == 110


def test_monitor_handles_short_tp_breach():
    closes = []
    monitor = MarkMonitor(InMemoryProtectionStore(), close_position=lambda symbol: closes.append(symbol), clock=lambda: 20)
    monitor.arm("ETHUSDT", "SHORT", 1, 105, 90, timestamp=19)
    events = monitor.on_mark("ETHUSDT", 89, timestamp=20)
    assert events[-1].kind == "CLOSED"
    assert closes == ["ETHUSDT"]


def test_stale_feed_parks_entries_and_emits_failure():
    monitor = MarkMonitor(InMemoryProtectionStore(), close_position=lambda symbol: None, stale_after=5, clock=lambda: 20)
    monitor.arm("BTCUSDT", "LONG", 1, 95, 110, timestamp=10)
    events = monitor.check_freshness()
    assert events[0].kind == "PROTECTION_FAILED"
    assert monitor.entries_parked
    assert monitor.state("BTCUSDT") is ProtectionState.DEGRADED


def test_monitor_restores_armed_protection_after_restart():
    store = InMemoryProtectionStore()
    first = MarkMonitor(store, close_position=lambda symbol: None, clock=lambda: 10)
    first.arm("BTCUSDT", "LONG", 1, 95, 110, timestamp=9)
    restored = MarkMonitor(store, close_position=lambda symbol: None, clock=lambda: 10)
    assert restored.get("BTCUSDT").stop_loss == 95
    assert restored.get("BTCUSDT").take_profit == 110
