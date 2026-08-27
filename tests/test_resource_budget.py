"""Continuous, fail-closed runtime resource budget for autonomous heavy work.

TDD for ``src.runtime.resource_budget``: a runtime guard that aborts long
in-process evaluation (walk-forward) before host exhaustion, WITHOUT ever
killing Hermes, deployed bots, databases, or unrelated services. It only ever
raises a catchable ``ResourceBudgetExceeded``.

RED phase: these tests reference ``ResourceBudget`` / ``ResourceBudgetExceeded``
which do not exist yet, so the file fails to import until GREEN.
"""
import threading
import time

import pytest

from scripts.resource_guard import GuardPolicy, ResourceSnapshot

from src.runtime.resource_budget import (
    ResourceBudget,
    ResourceBudgetExceeded,
)


def snap(**changes):
    values = dict(available_memory_bytes=2 * 1024**3, total_memory_bytes=4 * 1024**3,
                  swap_used_bytes=100, swap_total_bytes=1000, disk_free_bytes=20 * 1024**3,
                  disk_total_bytes=60 * 1024**3, disk_used_percent=40.0, inode_free_percent=80.0)
    values.update(changes)
    return ResourceSnapshot(**values)


def test_preflight_raises_when_violated():
    # Inject a snapshot source that reports low available memory.
    low_mem = snap(available_memory_bytes=500 * 1024**2)
    budget = ResourceBudget(snapshot_source=lambda: low_mem, policy=GuardPolicy())
    with pytest.raises(ResourceBudgetExceeded) as exc:
        budget.preflight()
    assert "LOW_AVAILABLE_MEMORY" in exc.value.violations
    # The exception is catchable: nothing was killed.
    assert exc.value.killed_anything is False


def test_preflight_ok_when_clean():
    budget = ResourceBudget(snapshot_source=lambda: snap(), policy=GuardPolicy())
    observed = budget.preflight()
    assert isinstance(observed, ResourceSnapshot)
    assert observed.available_memory_bytes == 2 * 1024**3


def test_assert_within_raises_on_breach():
    low_mem = snap(available_memory_bytes=500 * 1024**2)
    budget = ResourceBudget(snapshot_source=lambda: low_mem, policy=GuardPolicy())
    with pytest.raises(ResourceBudgetExceeded) as exc:
        budget.assert_within()
    assert "LOW_AVAILABLE_MEMORY" in exc.value.violations
    assert budget.breached is True


def test_assert_within_passes_when_clean():
    budget = ResourceBudget(snapshot_source=lambda: snap(), policy=GuardPolicy())
    # Must not raise.
    budget.assert_within()
    assert budget.breached is False


def test_context_manager_enters_and_exits_clean_when_ok():
    budget = ResourceBudget(snapshot_source=lambda: snap(), policy=GuardPolicy())
    with budget:
        pass
    # Clean exit should leave no breach.
    assert budget.breached is False


def test_context_manager_raises_on_breach_during_work_if_asserted():
    # Source is clean on enter but becomes violating by the time the block exits.
    holder = {"v": snap()}
    budget = ResourceBudget(snapshot_source=lambda: holder["v"], policy=GuardPolicy())
    with pytest.raises(ResourceBudgetExceeded):
        with budget:
            holder["v"] = snap(available_memory_bytes=400 * 1024**2)
    assert budget.breached is True


def test_invalid_interval_rejected():
    with pytest.raises(ValueError):
        ResourceBudget(snapshot_source=lambda: snap(), policy=GuardPolicy(),
                       sample_interval_seconds=0)


def test_budget_never_imports_killing_primitives():
    # The budget must observe only and never kill/restart anything. Prove the
    # module contains no process-killing primitives by inspecting its source.
    import inspect
    from src.runtime import resource_budget as rb_module
    source = inspect.getsource(rb_module)
    assert "os.kill" not in source
    assert "killpg" not in source
    assert "SIGKILL" not in source
    assert "SIGTERM" not in source
    assert "os.system" not in source


def test_watchdog_detects_breach_without_killing():
    # Source is clean on the first call, then violating on every later call.
    calls = {"n": 0}

    def source():
        calls["n"] += 1
        if calls["n"] == 1:
            return snap()
        return snap(available_memory_bytes=400 * 1024**2)

    budget = ResourceBudget(snapshot_source=source, policy=GuardPolicy(),
                            sample_interval_seconds=0.01, watchdog=True)
    budget.start_watchdog()
    try:
        # Give the daemon time to sample the violating state.
        time.sleep(0.15)
        assert budget.breached is True
        assert "LOW_AVAILABLE_MEMORY" in budget.breach_violations
    finally:
        budget.stop_watchdog()
    # Process is still alive and well: the test itself continues.
    assert budget.breached is True


def test_watchdog_stop_is_idempotent():
    budget = ResourceBudget(snapshot_source=lambda: snap(), policy=GuardPolicy(),
                            sample_interval_seconds=0.01, watchdog=True)
    budget.start_watchdog()
    budget.stop_watchdog()
    # Stopping again must not raise.
    budget.stop_watchdog()
    assert budget._thread is None
