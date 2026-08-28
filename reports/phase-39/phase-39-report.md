# Phase 39 — Scheduler-driven monitor tick closes the heartbeat breaker live (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-29 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline unit work + offline replay of synthetic in-repo datasets (zero network egress, zero orders)
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase is a runtime-liveness hardening stream and does not touch the deterministic gate. No promotion/selection/winner flag is emitted or flipped.

## Scope and why it is unblocked

The cron mandate lists `runtime health`, `protection`, and `reconciliation` as unblocked streams. Review P1-2 (from the prior review) required that the fail-closed breakers (`heartbeat`, `resource`) be tripped by an *independent* timer, not only by injected tests. The previous wiring (`AutonomousPaperRuntime.process` beats + ticks monitors) only runs when a snapshot arrives. When cycles *stop* arriving, nothing ticks the monitors, so a stalled runtime never trips the heartbeat breaker in production and the breaker is decorative.

This phase adds that independent monitor-tick path:
- `PaperScheduler` owns a monitor-tick step driven on a fixed cadence regardless of snapshot arrival (`monitor_tick` / `monitor_interval_seconds`, called inside `run()` and exposed as `tick_monitors_now()`).
- `MonitorWatchdog` is a standalone timer that calls a `tick` callable (wired to `runtime.tick_monitors`) on cadence, independent of cycles.
- `CanonicalOfflineRuntime.paper` builds a `MonitorWatchdog` when `monitor_interval_seconds` is given, and exposes `run_monitor_loop` / `start_monitor_loop` daemon-loop helpers.

The work was partially present from a prior session but was left in a **RED, undocumented** state: `tests/test_scheduler_monitor_loop.py` and `tests/test_monitor_watchdog.py` existed, but `test_scheduler_watchdog_step_trips_heartbeat_breaker_on_stall` FAILED, and `src/runtime/scheduler.py` carried a leftover mutation artifact. This run closed the loop GREEN, mutation-verified it, and documents it here (the prior Phase 38 report never mentioned this stream).

## What was broken (found this run)

`src/runtime/scheduler.py::tick_monitors_now` contained a leftover mutation artifact that disabled the wiring:

```python
def tick_monitors_now(self) -> None:
    if self.monitor_tick is not None:
        pass  # MUTATION: wiring disabled
        self._last_monitor_tick = self.clock()
```

The real `run()` loop (line 77) correctly calls `self.monitor_tick()`, but the test-only helper `tick_monitors_now` had been mutated to `pass` during a mutation check and **never reverted** — so the production helper was a no-op. That is exactly why `test_scheduler_watchdog_step_trips_heartbeat_breaker_on_stall` was RED: the watchdog-driven tick never evaluated the heartbeat monitor, so the breaker stayed closed on a stall.

## TDD cycle (strict)

### A. Scheduler monitor-tick step (`src/runtime/scheduler.py`)
- **RED (confirmed this run):** `tests/test_scheduler_monitor_loop.py::test_scheduler_watchdog_step_trips_heartbeat_breaker_on_stall` failed with `AssertionError: watchdog-driven monitor tick must trip on stall` (`breakers.is_open("heartbeat")` was `False`). The failure was a genuine missing-behavior failure caused by the `pass` no-op, not a typo.
- **GREEN:** reverted the mutation artifact so `tick_monitors_now` actually calls `self.monitor_tick()` (mirroring `run()`), then records the tick time. The test now trips the heartbeat breaker fail-closed on a stall and parks entries.
- **Mutation check (build-verification skill):** re-applied the `pass` mutation to `tick_monitors_now` -> the test went RED (exit 1); reverted -> GREEN. The assertion genuinely binds to the wiring.

### B. Canonical wrapper regression test (`tests/test_scheduler_monitor_loop.py`)
- The new wrapper methods `CanonicalOfflineRuntime.run_monitor_loop` / `start_monitor_loop` had **no direct test**, so a wiring-disabled wrapper would pass undetected (the same class of bug that broke `tick_monitors_now`). Added `test_canonical_start_monitor_loop_runs_watchdog`, which starts the loop, lets it run ~0.3s of wall time, and asserts the watchdog ticked (`tick_count >= 3`).
- **RED-by-design:** mutating `start_monitor_loop` to return a no-op task (`asyncio.create_task(asyncio.sleep(0))`) drives `tick_count == 0` and the test goes RED (exit 1). Reverted -> GREEN.
- **GREEN:** `tests/test_scheduler_monitor_loop.py` -> 4 passed (incl. the new test).

## What this run added / changed
- `src/runtime/monitor_watchdog.py` — NEW: `MonitorWatchdog` (standalone monitor-tick timer) + `wire_watchdog_to_runtime` helper. Pure offline host + liveness observation; no signed calls, no credentials, no orders.
- `src/runtime/scheduler.py` — MODIFIED: `monitor_tick` / `monitor_interval_seconds` params; `run()` drives the monitor tick on cadence; `tick_monitors_now()` helper (wiring fixed this run).
- `src/runtime/canonical.py` — MODIFIED: `paper()` builds a `MonitorWatchdog` when `monitor_interval_seconds` is set; adds `run_monitor_loop` / `start_monitor_loop`.
- `tests/test_monitor_watchdog.py` (5), `tests/test_scheduler_monitor_loop.py` (4, +1 new) — NEW TDD suites.
- `reports/phase-39/phase-39-report.md` — this report.

## Raw tests (executed this run)
```text
# confirm RED (the broken helper) before fixing
pytest tests/test_scheduler_monitor_loop.py::test_scheduler_watchdog_step_trips_heartbeat_breaker_on_stall -q
    -> 1 failed (AssertionError: watchdog-driven monitor tick must trip on stall)
# GREEN after reverting the mutation artifact in tick_monitors_now
pytest tests/test_scheduler_monitor_loop.py tests/test_monitor_watchdog.py -q
    -> 9 passed
# compileall
python3 -m compileall -q src scripts
    -> exit 0 (clean)
# full suite, no regressions
pytest tests/ -q
    -> 613 passed (before the additive wrapper test) ; 614 passed (after adding it)
# mutation checks (temporary, reverted):
#   tick_monitors_now -> pass  : test_scheduler_watchdog_step... -> 1 failed ; reverted -> pass
#   start_monitor_loop -> no-op : test_canonical_start_monitor_loop_runs_watchdog -> 1 failed ; reverted -> pass
```

## Offline runner evidence (no egress, synthetic in-repo harness)
Driven through the in-repo harness (`PaperScheduler` + `AutonomousPaperRuntime` + `FakeExchange` + `FakeProvider`, synthetic `MarketSnapshot`/`PortfolioView`):
- One healthy cycle at `t=NOW` beats the heartbeat -> `hb.status() == "HEALTHY"`.
- Advance the fake clock past `max_gap_ms` with no new cycles; call the scheduler's monitor-tick step (only path, never a manual `runtime.tick_monitors()`) -> `breakers.is_open("heartbeat") is True` and `breakers.entries_parked()` is True. A stalled runtime now trips the breaker fail-closed live.
- `CanonicalOfflineRuntime.paper(..., monitor_interval_seconds=0.05).start_monitor_loop()` actually starts a ticking `MonitorWatchdog` (`tick_count >= 3` over ~0.3s real time).

## Network calls
- **0 network calls this run.** All inputs are synthetic in-repo objects / fixtures. No `GET`, no authenticated, signed, or account endpoints were touched.

## Signed calls / orders / positions
- **Signed calls: 0.** Orders: 0. Positions: 0 (open or closed by this phase). No credentials, demo keys, or live keys were used. No signed exchange calls, transfers, withdrawals, or funded execution occurred. Egress: none.

## Trades / fees / funding / PnL
- **Trades executed by this phase: 0.** Fees: 0. Funding: 0. PnL: 0 realized — this is a runtime-liveness hardening change; it trades nothing and never flips the promotion gate.

## Protection / reconciliation
- The change *strengthens* the fail-closed protection path: a stalled runtime now parks new entries via the heartbeat breaker instead of leaving it decorative. No position, protection, or reconciliation path was otherwise altered. The watchdog is observation-only (ticks monitors; never signs, never orders).

## Limitations (honest)
- `MonitorWatchdog.run` uses `time.monotonic` by default; the daemon loop therefore stamps liveness in real wall time. The unit tests for `tick_monitors_now` / the canonical wrapper inject a fake clock only at the monitor layer (`HeartbeatMonitor`/`ResourceMonitor` clock), so the stall-detect behavior is exercised deterministically while the loop cadence itself is real-time in the wrapper test (acceptable: it proves the loop *runs and ticks*).
- The breaker still only trips for monitors that are *attached*; a runtime constructed without a heartbeat monitor will not have a heartbeat breaker to trip. That is by design (the runtime wires monitors in `paper()`).
- No promotion implied. The deterministic baseline is negative and unchanged; this phase is liveness hardening only.

## Phase 6 promotion gate
- **Still BLOCKED.** This phase adds an independent monitor-tick path for runtime health. The deterministic baseline remains negative; no promotion action was taken and none is authorized while the baseline is negative.

## Commit / push
- New/changed: `src/runtime/monitor_watchdog.py`, `src/runtime/scheduler.py`, `src/runtime/canonical.py`, `tests/test_monitor_watchdog.py`, `tests/test_scheduler_monitor_loop.py`, `reports/phase-39/phase-39-report.md`.
- Git identity verified: `user.name=𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟`, `user.email=42990222+hernanda-git@users.noreply.github.com` (matches `gh api`).
- Secret scan: `.env` is git-ignored; content scan over tracked + new text found **0 secret hits**. Verified repeatable, network-free, secret-free command: `pytest tests/test_scheduler_monitor_loop.py tests/test_monitor_watchdog.py -q`.
- **Resource guard (this run):** `ok=true`, swap_used_percent=87.2% (under 90% cap; 266 MB free), disk 45.8% used / 31.6 GB free, 49.9% inodes free. Heavy work proceeded; no exhaustion.
