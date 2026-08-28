# Phase 32 — Host resource pressure wired into fail-closed entry-parking breaker (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-28 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline control-layer engineering, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate explicitly lists `runtime health` and `resource safety` as unblocked
streams. Inspection of the standing scaffold found a real gap: `BreakerRegistry` and
`HeartbeatMonitor` existed and were unit-tested, but **no running loop ever consumed the
breaker registry to park entries** — `AutonomousPaperRuntime.process()` only honored the
provider circuit. So resource/heartbeat breakers were designed controls that never
actually stopped an entry. This phase closes that gap and adds a first-class
`resource` breaker driven by `scripts/resource_guard` (RAM, swap, disk, inodes).

1. **Added `resource` to `BREAKER_NAMES`** in `src/policy/breakers.py` (consistent with the
   existing `heartbeat` breaker).
2. **New `src/runtime/resource_monitor.py`** — `ResourceMonitor` mirrors `HeartbeatMonitor`:
   observes host resources via `scripts.resource_guard.snapshot`/`violations`, and on a
   violation trips the `resource` breaker fail-closed, parking entries. A clean sample after
   pressure clears only a monitor-raised trip via verified `auto_recovery`; an operator trip
   is preserved. Cold start is `UNKNOWN` (never parks a fresh runtime). A snapshot error is
   treated fail-closed as `DEGRADED`.
3. **`AutonomousPaperRuntime` now honors an open breaker registry** — `process()` parks new
   entries when `breakers.entries_parked()` (first time the composition root consumes the
   breaker registry; fail-closed, model cannot open/clear a breaker).
4. **`/api/state` truthfully projects open breakers** — reads the same breaker store the
   runtime writes and reports `path_present=False` when absent instead of inventing a state.

## TDD cycle (strict)

- **RED:** `tests/test_resource_monitor.py` (10 tests) written before the module existed.
  Collection failed: `ModuleNotFoundError: No module named 'src.runtime.resource_monitor'`
  (feature absent, not a typo). The runtime/UI integration tests were written against the
  not-yet-wired surface and also failed until implementation landed.
- **GREEN:** Implemented `ResourceMonitor` (status UNKNOWN/HEALTHY/DEGRADED, `should_park`
  fail-closed, `tick` trips/clears the `resource` breaker), added `resource` to
  `BREAKER_NAMES`, wired `breakers` into `AutonomousPaperRuntime.process`, and added the
  `breakers` surface to `ledger_state()`. Combined run of the three touched test files:
  **26 passed**.
- **REFACTOR:** No behavior change beyond the minimal implementation; injection seams
  (`snapshot_source`, `policy`, `clock`, `breakers`) kept for testing; no duplication.
- **Mutation check (build-verification skill):**
  - Disabling the trip guard (`if not self._registry.is_open(BREAKER_NAME):` -> `if False:`) in
    `resource_monitor.py` made **4** resource tests FAIL (`test_degraded_trips_resource_breaker_and_parks_entries`,
    `test_recovery_after_degraded_clears_breaker_via_auto_recovery`,
    `test_tick_does_not_recover_without_clearing_violation`,
    `test_integration_parks_and_recovers_over_sample_stream`). Reverted -> 10 passed.
  - Disabling the runtime park check (`self.breakers.entries_parked()` -> `False`) in
    `paper_runtime.py` made **2** runtime tests FAIL (`test_runtime_parks_entries_when_a_breaker_is_open`,
    `test_resource_pressure_end_to_end_parks_entries`). Reverted -> 6 passed.
  Both reverted and re-green; the assertions genuinely bind to the guards.

## Raw tests (executed this run)

```text
pytest tests/test_resource_monitor.py tests/test_paper_runtime.py tests/test_ui_state_api.py -q
  -> 26 passed
pytest tests/ -q                                  -> 531 passed (was 516; +15 new cases)  [background]
python3 -m compileall -q src scripts tests        -> exit 0 (clean)
python3 -m pytest tests/test_resource_monitor.py  -> 10 passed   (post-mutation-revert)
python3 -m pytest tests/test_paper_runtime.py     -> 6 passed    (post-mutation-revert)
```

Imports of the composition root verified clean under the real path (Python 3.12.3):
`import src.runtime.paper_runtime, src.runtime.resource_monitor, scripts.ui_server, src.policy.breakers` -> OK.

## Network calls

**None.** `ResourceMonitor` reads only `/proc/meminfo` and `os.statvfs` via
`scripts.resource_guard.snapshot` (host observation). No public Bitget calls, no signed
calls, no credentials, no orders. This is a deterministic control-layer change.

Resource guard preflight (run at start of this run) reported the host healthy:
`available_memory_bytes=1286508544`, `disk_used_percent=45.7`, `swap_used_percent=69.3`,
`inode_free_percent=50.0`, `violations=[]` -> `ok=true`. So on this host no resource breach
would trip the new breaker; the trip path is exercised only by the injected test snapshots.

## Signed calls / orders / positions

- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed by this phase). Control-layer
  engineering only; no credentials, demo keys, or live keys used; no signed exchange calls,
  transfers, withdrawals, or funded execution occurred.

## Trades / fees / funding / PnL

Not applicable. This phase changes entry-parking policy, not strategy evaluation. No
`SIGNED`-call replay, no new PnL measurement. The negative deterministic baseline (Phase 6
blocked) is unchanged and untouched.

## Protection / reconciliation

- The new `resource` breaker parks NEW entries fail-closed; it does not close or alter
  existing positions, so it composes safely with the protection supervisor and reconciliation
  read-back (both still covered by their own suites, part of the 531 passing tests). The
  `ResourceMonitor` follows the same model-independence rule as `HeartbeatMonitor`: the model
  can never open or clear the `resource` breaker.
- End-to-end test `test_resource_pressure_end_to_end_parks_entries` drives the real
  `ResourceMonitor` -> `BreakerRegistry` -> `AutonomousPaperRuntime.process` path with an
  injected degraded host snapshot and asserts no order is placed and the cycle is parked
  `BREAKER_OPEN`.

## Dashboard truthfulness

`/api/state` now includes `breakers: {open, reason_codes, path_present}`. When the breaker
store is absent (fresh environment) it returns `{"open": [], "reason_codes": [],
"path_present": false}` rather than inventing a healthy state. When a `resource` breaker is
open it projects `open: ["resource"]` and `reason_codes: ["RESOURCE_BREAKER"]`. No credentials
or signed-call surface is added (asserted: `BITGET_API_SECRET` not in the serialized body).

## Honest findings

- **Closed a real gap:** breakers (heartbeat, and now resource) existed as tested components
  but were never consumed by the runtime loop. `AutonomousPaperRuntime` now honors an open
  breaker registry fail-closed, so host resource pressure (and any other breaker) actually
  stops new entries. This is the first time the composition root enforces the breaker system
  the architecture already described.
- **Fail-closed by construction:** cold start is `UNKNOWN` (never parks a fresh runtime);
  a sample-observation error is treated as pressure (we must not assume health when we cannot
  measure it); only `operator` or a verified `auto_recovery` (clean sample) may clear a trip;
  a monitor never clears an operator-initiated trip.
- **No promotion, no LLM, no execution:** deterministic baseline stays negative; Phase 6
  selection remains blocked. This phase is pure safety/control engineering on an unblocked
  stream.

## Limitations (honest)

- The `ResourceMonitor` is the component that trips the breaker; driving it each cycle
  requires a scheduler/runtime loop. This phase wires the *consumption* side (the runtime
  honors an open breaker) and the *component*, but the standing scaffold still has no
  scheduler that calls `mon.tick()` on a timer (same status as `HeartbeatMonitor`). The
  breaker-trip path is therefore verified via injected tests, not yet via a live loop. This
  is a known, bounded limitation, not a claim of live integration.
- `scripts/resource_guard.py` is a preflight/continuous in-process guard (raises
  `ResourceBudgetExceeded`); `ResourceMonitor` is the runtime-health *breaker* integration
  (trip/clear in the registry). They share the same `GuardPolicy`/`violations` primitives but
  are distinct controls: one aborts heavy in-process work, the other parks autonomous entries.
- Host observation reads `/proc/meminfo` + `statvfs` (Linux). Behavior on non-Linux hosts is
  untested (the guard would raise on snapshot and the monitor would fail-closed to `DEGRADED`).

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. This phase strengthens runtime health and resource safety (both
explicitly unblocked) and makes the existing breaker system actually effective. Unblocked
research/engineering continues per the cron mandate.

## Commit / publish

- `e956aaf feat(evaluation): fail-closed network-evidence rollup (phase 31 source)` — commits
  the previously-pending Phase 31 source (evidence_rollup + test + summary script; the
  phase-31 report .md/.json are gitignored by repo convention).
- `88e97d3 feat(runtime): wire host resource pressure into fail-closed entry-parking breaker
  (phase 32, TDD + mutation-verified)`.
- Pushed to `origin/master` (92ec40d..88e97d3). Content-level secret scan: 0 hits. Published
  tree grep for `.env$/private_key/config.json$`: clean. Repo is public.
