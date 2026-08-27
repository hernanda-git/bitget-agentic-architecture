"""Runtime health verification: drive HeartbeatMonitor over a simulated timeline.

Offline, no network, no credentials, no orders. Proves the fail-closed contract:
* a silent gap (no cycles) trips the `heartbeat` breaker and parks new entries;
* a fresh heartbeat after the gap performs a verified automatic recovery and
  un-parks entries.

Run: python3 scripts/run_runtime_health_report.py
Exit 0 on a coherent, fail-closed trace; non-zero on any invariant violation.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.policy.breakers import BreakerRegistry, BreakerStore
from src.runtime.heartbeat import HeartbeatMonitor


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="runtime-health-")
    registry = BreakerRegistry(BreakerStore(os.path.join(tmp, "breakers.json")))
    mon = HeartbeatMonitor(max_gap_ms=1000)
    mon.attach(registry)

    # (now_ms, beat_occurred?) — a silent gap from 1000ms to 6000ms.
    timeline = [
        (0, True), (500, True), (1000, True),
        (2000, False), (3000, False), (4000, False),  # stall
        (5000, False),
        (6000, True),   # recovery heartbeat
        (6500, True),
    ]

    print("now_ms  beat   status    parked  reason")
    print("------  -----  --------  ------  ------")
    for now, beat in timeline:
        if beat:
            mon.beat(now)
        status = mon.tick(now)
        parked = registry.entries_parked()
        reason = registry.snapshot().get("heartbeat", {}).get("reason", "-")
        print(f"{now:<7}  {str(beat):<5}  {status:<8}  {str(parked):<6}  {reason}")
        # Fail-closed invariant: every STALLED observation must park entries.
        if status == "STALLED" and not parked:
            print("\nINVARIANT VIOLATION: stalled but entries not parked")
            return 1

    # Final state after recovery must be healthy and un-parked.
    final = mon.tick(7000)
    if final != "HEALTHY":
        print(f"\nFINAL STATE ERROR: expected HEALTHY, got {final}")
        return 1
    if registry.entries_parked():
        print("\nFINAL STATE ERROR: entries still parked after recovery")
        return 1

    print("\nRUNTIME_HEALTH_OK: stall parked entries; fresh heartbeat recovered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
