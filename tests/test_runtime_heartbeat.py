"""Runtime heartbeat / stall monitor for daemon liveness (TDD: RED first).

A daemon can emit perfectly-formed, perfectly-constant payloads forever and pass
every health check while computing nothing (see build-verification skill). The
heartbeat monitor detects *liveness regression*: if the autonomous runtime stops
producing cycles for longer than ``max_gap_ms``, it is STALLED and must park new
entries fail-closed via the ``heartbeat`` breaker. A fresh heartbeat is a verified
automatic recovery that clears the monitor's own trip.

No signed calls, no credentials, no orders. Pure offline measurement.
"""
from pathlib import Path

import pytest

from src.policy.breakers import BreakerRegistry, BreakerStore
from src.runtime.heartbeat import HeartbeatMonitor

ROOT = Path(__file__).resolve().parents[1]


def _registry(tmp_path: Path) -> BreakerRegistry:
    return BreakerRegistry(BreakerStore(tmp_path / "breakers.json"))


def test_heartbeat_monitor_module_and_class_exist():
    assert HeartbeatMonitor is not None


def test_healthy_within_gap():
    mon = HeartbeatMonitor(max_gap_ms=1000)
    mon.beat(0)
    assert mon.status(0) == "HEALTHY"
    assert mon.status(999) == "HEALTHY"
    assert mon.is_stalled(999) is False
    assert mon.should_park(999) is False


def test_stalled_after_gap_exceeded():
    mon = HeartbeatMonitor(max_gap_ms=1000)
    mon.beat(0)
    # Exactly at the boundary is still healthy; one ms over is stalled.
    assert mon.status(1000) == "HEALTHY"
    assert mon.status(1001) == "STALLED"
    assert mon.is_stalled(1001) is True
    assert mon.should_park(1001) is True


def test_unknown_before_first_beat_cold_start_not_parked():
    mon = HeartbeatMonitor(max_gap_ms=1000)
    # Never beat: cold start. Do not park a fresh runtime before any cycle.
    assert mon.status(5000) == "UNKNOWN"
    assert mon.is_stalled(5000) is False
    assert mon.should_park(5000) is False


def test_rejects_non_positive_gap():
    with pytest.raises(ValueError):
        HeartbeatMonitor(max_gap_ms=0)
    with pytest.raises(ValueError):
        HeartbeatMonitor(max_gap_ms=-5)


def test_rejects_regressed_beat_timestamp():
    mon = HeartbeatMonitor(max_gap_ms=1000)
    mon.beat(5000)
    with pytest.raises(ValueError):
        mon.beat(4000)


def test_stall_trips_heartbeat_breaker_and_parks_entries(tmp_path: Path):
    reg = _registry(tmp_path)
    mon = HeartbeatMonitor(max_gap_ms=1000)
    mon.attach(reg)
    mon.beat(0)
    # Advance past the gap without a beat -> tick must trip the breaker.
    assert mon.tick(1001) == "STALLED"
    assert reg.is_open("heartbeat") is True
    assert reg.entries_parked() is True
    # The trip is attributed to the monitor, not an operator override.
    assert "HEARTBEAT_BREAKER" in reg.reason_codes()


def test_fresh_beat_after_stall_clears_breaker_via_auto_recovery(tmp_path: Path):
    reg = _registry(tmp_path)
    mon = HeartbeatMonitor(max_gap_ms=1000)
    mon.attach(reg)
    mon.beat(0)
    mon.tick(1001)  # stall -> trip
    assert reg.is_open("heartbeat") is True
    mon.beat(1002)  # fresh heartbeat -> verified auto-recovery
    assert reg.is_open("heartbeat") is False
    assert reg.entries_parked() is False
    assert mon.status(1002) == "HEALTHY"


def test_monitor_does_not_clear_operator_tripped_breaker(tmp_path: Path):
    reg = _registry(tmp_path)
    mon = HeartbeatMonitor(max_gap_ms=1000)
    mon.attach(reg)
    # Operator manually trips the heartbeat breaker.
    reg.trip("heartbeat", "operator intervention")
    mon.beat(0)
    # Even though we later observe a stall and then a fresh beat, the monitor must
    # NOT clear an operator-initiated trip (operator authority preserved).
    mon.tick(1001)
    assert reg.is_open("heartbeat") is True
    mon.beat(1002)
    assert reg.is_open("heartbeat") is True  # still open: operator must clear
    # Only the operator may clear it.
    reg.clear("heartbeat", actor="operator")
    assert reg.is_open("heartbeat") is False


def test_tick_does_not_recover_without_fresh_beat(tmp_path: Path):
    reg = _registry(tmp_path)
    mon = HeartbeatMonitor(max_gap_ms=1000)
    mon.attach(reg)
    mon.beat(0)
    mon.tick(1001)  # stall -> trip
    assert reg.is_open("heartbeat") is True
    # Without a fresh beat the gap keeps growing, so liveness stays stalled and the
    # breaker stays open (fail-closed: entries remain parked).
    mon.tick(2000)
    assert mon.is_stalled(2000) is True
    assert reg.is_open("heartbeat") is True
    assert reg.entries_parked() is True


def test_integration_parks_and_recovers_over_timestamp_stream(tmp_path: Path):
    """Drive a realistic timeline with one silent gap.

    Asserts the fail-closed invariant: every STALLED observation must park entries,
    and a fresh heartbeat after the gap must recover.
    """
    reg = _registry(tmp_path)
    mon = HeartbeatMonitor(max_gap_ms=1000)
    mon.attach(reg)
    # (now_ms, beat_occurred?)
    timeline = [
        (0, True), (500, True), (1000, True),
        (2000, False), (3000, False), (4000, False),  # silent gap -> stalled
        (5000, False),
        (6000, True),   # recovery heartbeat
        (6500, True),
    ]
    for now, beat in timeline:
        if beat:
            mon.beat(now)
        st = mon.tick(now)
        parked = reg.entries_parked()
        if st == "STALLED":
            assert parked is True, f"stall at {now} must park entries"
    # After recovery the runtime is healthy and un-parked.
    assert mon.tick(7000) == "HEALTHY"
    assert reg.entries_parked() is False
