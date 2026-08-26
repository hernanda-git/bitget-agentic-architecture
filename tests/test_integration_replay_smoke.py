"""Build-verification integration replay smoke (driven via pytest).

Mirrors scripts/ci_replay_smoke.run_smoke but asserts the same zero-crash and
decision-mix contract inside the durable test suite. No network, no signed
calls, no live exchange: only FakeProvider + FakeExchange + the real
CanonicalOfflineRuntime composition root.
"""
from pathlib import Path

import scripts.ci_replay_smoke as smoke


def test_replay_smoke_has_zero_crashes_and_sane_decision_mix(tmp_path):
    result = smoke.run_smoke(tmp_path / "smoke.sqlite3")

    assert result["crashes"] == 0, result
    assert result["messages"] == 120
    assert result["terminal_events"] == 120, result
    assert result["orders_placed"] > 0, result
    # A degenerate router (all one bucket) would fail this: we require the
    # composition root to actually route ENTER / HOLD / rejection / staleness
    # to distinct terminal dispositions.
    assert {"EXECUTED", "HELD", "REJECTED", "PARKED"} <= set(result["statuses"]), result
    assert result["distinct_statuses"] >= 4, result
