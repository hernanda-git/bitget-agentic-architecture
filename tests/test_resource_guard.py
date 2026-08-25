from pathlib import Path

from scripts.resource_guard import GuardPolicy, ResourceSnapshot, violations


def snap(**changes):
    values = dict(available_memory_bytes=2 * 1024**3, total_memory_bytes=4 * 1024**3,
                  swap_used_bytes=100, swap_total_bytes=1000, disk_free_bytes=20 * 1024**3,
                  disk_total_bytes=60 * 1024**3, disk_used_percent=40.0, inode_free_percent=80.0)
    values.update(changes)
    return ResourceSnapshot(**values)


def test_healthy_snapshot_has_no_violations():
    assert violations(snap()) == []


def test_low_memory_blocks_before_launch():
    assert "LOW_AVAILABLE_MEMORY" in violations(snap(available_memory_bytes=500 * 1024**2))


def test_swap_disk_and_inode_pressure_are_independent_guards():
    result = violations(snap(swap_used_bytes=950, disk_used_percent=90, disk_free_bytes=2 * 1024**3, inode_free_percent=5))
    assert result == ["SWAP_PRESSURE", "DISK_PRESSURE", "LOW_DISK_FREE", "INODE_PRESSURE"]


def test_policy_can_be_tightened_for_small_test_hosts():
    policy = GuardPolicy(min_available_memory_mb=3072, max_swap_used_percent=5)
    assert set(violations(snap(), policy)) == {"LOW_AVAILABLE_MEMORY", "SWAP_PRESSURE"}
