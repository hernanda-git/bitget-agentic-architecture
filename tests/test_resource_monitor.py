"""Runtime host-resource pressure monitor (TDD: RED first).

Host resource pressure (low memory, swap, disk, inode) is observed via
``scripts.resource_guard`` and, when a violation is present, trips the
``resource`` breaker in the ``BreakerRegistry``, parking new entries
fail-closed. When the violation clears, a monitor-raised trip is cleared via
verified auto-recovery. The model can never clear the breaker.

No signed calls, no credentials, no orders. Pure offline host observation.

Mirrors ``tests/test_runtime_heartbeat.py`` (cold start UNKNOWN, fail-closed
park, auto-recovery clears only monitor-raised trips, operator authority
preserved).
"""
from pathlib import Path

import pytest

from scripts.resource_guard import GuardPolicy, ResourceSnapshot
from src.policy.breakers import BreakerRegistry, BreakerStore
from src.runtime.resource_monitor import ResourceMonitor

ROOT = Path(__file__).resolve().parents[1]


def _registry(tmp_path: Path) -> BreakerRegistry:
    return BreakerRegistry(BreakerStore(tmp_path / "breakers.json"))


def _healthy_snapshot() -> ResourceSnapshot:
    return ResourceSnapshot(
        available_memory_bytes=2 * 1024**3,
        total_memory_bytes=4 * 1024**3,
        swap_used_bytes=0,
        swap_total_bytes=2 * 1024**3,
        disk_free_bytes=30 * 1024**3,
        disk_total_bytes=64 * 1024**3,
        disk_used_percent=40.0,
        inode_free_percent=50.0,
    )


def _degraded_snapshot() -> ResourceSnapshot:
    # Several violations at once: low memory, full swap, near-full disk, low inodes.
    return ResourceSnapshot(
        available_memory_bytes=1,
        total_memory_bytes=4 * 1024**3,
        swap_used_bytes=2 * 1024**3,
        swap_total_bytes=2 * 1024**3,
        disk_free_bytes=1,
        disk_total_bytes=64 * 1024**3,
        disk_used_percent=99.0,
        inode_free_percent=1.0,
    )


def test_resource_monitor_module_and_class_exist():
    assert ResourceMonitor is not None


def test_cold_start_unknown_not_degraded_and_not_parked():
    mon = ResourceMonitor(policy=GuardPolicy(), snapshot_source=_healthy_snapshot)
    # Before any sample: cold start. Do not park a fresh runtime.
    assert mon.status(5000) == "UNKNOWN"
    assert mon.is_degraded(5000) is False
    assert mon.should_park(5000) is False


def test_healthy_sample_is_not_degraded_and_not_parked():
    mon = ResourceMonitor(policy=GuardPolicy(), snapshot_source=_healthy_snapshot)
    assert mon.tick(1000) == "HEALTHY"
    assert mon.is_degraded(1000) is False
    assert mon.should_park(1000) is False


def test_degraded_sample_is_degraded_and_parks():
    mon = ResourceMonitor(policy=GuardPolicy(), snapshot_source=_degraded_snapshot)
    st = mon.tick(1000)
    assert st == "DEGRADED"
    assert mon.is_degraded(1000) is True
    assert mon.should_park(1000) is True
    # The observed violations are recorded and non-empty.
    assert mon.violations == ["LOW_AVAILABLE_MEMORY", "SWAP_PRESSURE",
                              "DISK_PRESSURE", "LOW_DISK_FREE", "INODE_PRESSURE"]


def test_snapshot_error_is_fail_closed_degraded_and_parks():
    def boom():
        raise OSError("cannot read /proc/meminfo")

    mon = ResourceMonitor(policy=GuardPolicy(), snapshot_source=boom)
    # Observation failure must be treated as pressure (fail-closed), not UNKNOWN.
    assert mon.tick(1000) == "DEGRADED"
    assert mon.is_degraded(1000) is True
    assert mon.should_park(1000) is True
    assert "SNAPSHOT_ERROR" in mon.violations


def test_degraded_trips_resource_breaker_and_parks_entries(tmp_path: Path):
    reg = _registry(tmp_path)
    mon = ResourceMonitor(policy=GuardPolicy(), snapshot_source=_degraded_snapshot)
    mon.attach(reg)
    assert mon.tick(1000) == "DEGRADED"
    assert reg.is_open("resource") is True
    assert reg.entries_parked() is True
    assert "RESOURCE_BREAKER" in reg.reason_codes()


def test_recovery_after_degraded_clears_breaker_via_auto_recovery(tmp_path: Path):
    reg = _registry(tmp_path)
    mon = ResourceMonitor(policy=GuardPolicy(), snapshot_source=_degraded_snapshot)
    mon.attach(reg)
    mon.tick(1000)  # degraded -> trip
    assert reg.is_open("resource") is True
    # Switch the source to healthy and re-sample: verified auto-recovery.
    mon._snapshot_source = _healthy_snapshot
    assert mon.tick(1001) == "HEALTHY"
    assert reg.is_open("resource") is False
    assert reg.entries_parked() is False
    assert mon.status(1001) == "HEALTHY"


def test_monitor_does_not_clear_operator_tripped_breaker(tmp_path: Path):
    reg = _registry(tmp_path)
    mon = ResourceMonitor(policy=GuardPolicy(), snapshot_source=_degraded_snapshot)
    mon.attach(reg)
    # Operator manually trips the resource breaker.
    reg.trip("resource", "operator intervention")
    mon.tick(1000)  # degraded but already open
    # Even after the pressure clears, the monitor must NOT clear an
    # operator-initiated trip (operator authority preserved).
    mon._snapshot_source = _healthy_snapshot
    mon.tick(1001)
    assert reg.is_open("resource") is True  # still open: operator must clear
    reg.clear("resource", actor="operator")
    assert reg.is_open("resource") is False


def test_tick_does_not_recover_without_clearing_violation(tmp_path: Path):
    reg = _registry(tmp_path)
    mon = ResourceMonitor(policy=GuardPolicy(), snapshot_source=_degraded_snapshot)
    mon.attach(reg)
    mon.tick(1000)  # trip
    assert reg.is_open("resource") is True
    # Source stays degraded: breaker stays open (fail-closed).
    mon.tick(2000)
    assert mon.is_degraded(2000) is True
    assert reg.is_open("resource") is True
    assert reg.entries_parked() is True


def test_integration_parks_and_recovers_over_sample_stream(tmp_path: Path):
    """Drive a realistic timeline with one pressure episode.

    Asserts the fail-closed invariant: every DEGRADED observation must park
    entries, and clearing the pressure must recover.
    """
    reg = _registry(tmp_path)
    source = {"healthy": True}
    mon = ResourceMonitor(
        policy=GuardPolicy(),
        snapshot_source=lambda: _healthy_snapshot() if source["healthy"] else _degraded_snapshot(),
    )
    mon.attach(reg)
    timeline = [
        (0, True), (500, True), (1000, True),
        (2000, False), (3000, False), (4000, False),  # pressure episode
        (5000, False),
        (6000, True),   # recovered
        (6500, True),
    ]
    for now, healthy in timeline:
        source["healthy"] = healthy
        st = mon.tick(now)
        parked = reg.entries_parked()
        if st == "DEGRADED":
            assert parked is True, f"degraded at {now} must park entries"
    # After recovery the runtime is healthy and un-parked.
    assert mon.tick(7000) == "HEALTHY"
    assert reg.entries_parked() is False
