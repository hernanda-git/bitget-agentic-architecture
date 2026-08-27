# Phase 13 — Runtime Resource Safety: continuous fail-closed ResourceBudget (unblocked)

**Generated (WIB / Asia/Jakarta):** 2026-08-27 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** resource-safety engineering, offline, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `resource safety` as an unblocked work stream. The project
already had a `scripts/resource_guard.py` that performs a ONE-SHOT preflight before
launching a child process. What was missing: a CONTINUOUS, in-process resource budget
that aborts a long walk-forward / multi-engine evaluation (which can run for minutes
and allocate heavily) fail-closed *before* the host exhausts memory, swap, disk, or
inodes — and which does so WITHOUT ever killing Hermes, deployed bots, databases, or
any unrelated service.

This phase adds `src/runtime/resource_budget.py` (`ResourceBudget` +
`ResourceBudgetExceeded`), wires it into the two heavy measurement scripts
(`evaluate_candidate_family.py`, `evaluate_real_history.py`) and into the
`evaluate_candidate_family` orchestrator, and proves the behavior with strict TDD.

It is measurement/evaluation safety only. No strategy is selected, no order is placed,
and the `NEGATIVE_NET_PNL` deterministic gate is untouched.

## TDD cycle (strict)

- **RED:** `tests/test_resource_budget.py` was written first, importing
  `ResourceBudget` / `ResourceBudgetExceeded` which did not exist. Run failed:
  `ModuleNotFoundError: No module named 'src.runtime.resource_budget'`.
- **GREEN:** Implemented the module (observe-only; raises a catchable exception).
  `tests/test_resource_budget.py` -> 10 passed.
- **Integration RED->GREEN:** Added `resources_budget=None` param to
  `evaluate_candidate_family` and two integration tests:
  - `test_evaluate_candidate_family_invokes_resource_budget_per_candidate` (RED:
    budget not invoked; GREEN: preflight called once, assert_within once per candidate).
  - `test_evaluate_candidate_family_aborts_fail_closed_when_budget_breaches` (RED:
    breach ignored; GREEN: the 2nd candidate's `assert_within` raises
    `ResourceBudgetExceeded` and `run_baseline` was called for only 1 of 3 candidates).
- Refactor: loosened the annotated type to `Any` (the budget is duck-typed) and
  removed the unused import; argparse boolean flags switched to
  `action=argparse.BooleanOptionalAction` (the `/` shorthand mangles the dest name
  without it — this was caught by the existing `test_public_history.py` suite, which
  failed with `AttributeError: 'Namespace' object has no attribute 'resource_budget'`
  and was fixed).

## Raw tests (executed this run)

```text
pytest tests/test_resource_budget.py -q            -> 10 passed
pytest tests/test_evaluate_candidate_family.py -q -> 18 passed
pytest tests/ -q                                   -> 364 passed  (no regressions vs 352 baseline + 12 new)
python3 -m compileall -q src scripts tests         -> exit 0 (clean)
```

New behavior coverage (mutation-checked, see below):
- `ResourceBudget.preflight()` raises `ResourceBudgetExceeded` when the host already
  violates the policy (catches `LOW_AVAILABLE_MEMORY`, `SWAP_PRESSURE`, `DISK_PRESSURE`,
  `LOW_DISK_FREE`, `INODE_PRESSURE`).
- `ResourceBudget.assert_within()` raises on a mid-run breach.
- Context manager: clean enter/exit leaves no breach; a breach that appears before
  exit is raised on `__exit__`.
- Watchdog (optional daemon thread) detects a breach and records it without raising or
  killing inside the thread; the next `assert_within()` / context exit surfaces it.
- `evaluate_candidate_family` invokes `preflight()` once and `assert_within()` once per
  candidate, and aborts fail-closed on breach (later candidates never replay).

## Mutation test (assertions are real, not decoration)

Disabled the breach raise in `assert_within` (`if problems:` -> `if False:`, backup
restored afterward):

```text
pytest tests/test_resource_budget.py tests/test_evaluate_candidate_family.py -q
  FAILED test_assert_within_raises_on_breach
  FAILED test_context_manager_raises_on_breach_during_work_if_asserted
  2 failed, 16 passed      <- exactly the breach-binding assertions went red
```

Restored the file -> 18 passed. The mutation broke ONLY the two tests that assert the
breach behavior, proving the assertions bind to the real guard.

## End-to-end runtime verification (real code paths, no network/credentials)

All runs used stored public datasets (`data/history/*.json`, git-ignored); no `--fetch`,
no signed calls, no live/demo credentials.

- **A. `evaluate_real_history.py` budget ON (default), BTCUSDT_1m stored:**
  exit 0, output written, `net_pnl = -6872.31` (honest, matches phase-12 baseline for
  that dataset). Budget observed host state and stayed within limits.
- **B. Forced preflight breach (`--resource-min-memory-mb 100000000`):**
  exit 1, NO output written, traceback ends in
  `ResourceBudgetExceeded: resource budget exceeded: ['LOW_AVAILABLE_MEMORY']`.
  Fail-closed: heavy work aborted and the process raised a CATCHABLE exception — nothing
  was killed or restarted.
- **C. Budget bypass (`--no-resource-budget`):** exit 0, output written. The opt-out
  works for constrained environments that supply their own isolation.
- **D. `evaluate_candidate_family.py` budget ON, synthetic TINYUSDT_1m (150 candles):**
  exit 0, family output written with `selection_blocked: true`,
  `family_adequate_sample: true`, `candidates: 1`. (Tiny dataset is a smoke of the
  script's budget construction; it is not a profitability claim.)

## Network calls

- **0** network requests for every run above (offline stored-dataset replay).
- `request_evidence` for the measurement runs would be: requests=0, successes=0,
  failures=0, rate_limits=0, retries=0, schema_rejections=0, policy_rejections=0,
  signed_calls=0, orders=0, credentials_used=False.

## Signed calls / orders / positions

- **Signed calls: 0. Orders: 0. Positions: 0 (open or closed by this phase).**
  This is a resource-safety / evaluation-engineering phase; no execution path was
  exercised. No credentials, demo keys, or live keys were used. The only venue product
  referenced anywhere is `SUSDT-FUTURES` (public unauthenticated history), never
  `USDT-FUTURES`.

## Trades / fees / funding / PnL

- No trades were opened or closed by this phase. The numbers above
  (`net_pnl = -6872.31` for BTCUSDT_1m, reported in run A) are produced by the
  cost-inclusive deterministic replay engine over previously-acquired public history;
  they are measurement facts, not realized PnL, and they remain negative.
- `ResourceBudget` itself performs no trading, fee, funding, or PnL computation.

## Protection / reconciliation

- Not exercised by this phase (no positions were created), consistent with it being
  evaluation-only. Protection supervision and reconciliation read-back remain covered
  by their own suites (`test_protection_supervisor.py`, `test_protection_reconciliation.py`,
  `test_reconciliation.py`), which are part of the 364 passing tests. The budget does
  not interact with protection/reconciliation; it is a host-resource guard that runs
  orthogonally and parks heavy work without touching runtime trading state.

## Limitations (honest)

- `ResourceBudget` OBSERVES host state via discrete snapshots; it cannot prevent a
  single in-process allocation that exceeds available memory between two samples. The
  watchdog interval bounds detection latency (default 5s; configurable via
  `--resource-interval`). It is a guard, not a memory allocator.
- It complements but does not replace `scripts/resource_guard.run_bounded`, which still
  enforces hard `RLIMIT_AS`/`RLIMIT_CPU`/`RLIMIT_FSIZE` on spawned child processes.
  The two are layered: preflight + continuous budget for in-process work, rlimits for
  child isolation.
- The budget reuses the same `GuardPolicy` thresholds as the preflight. A tighter policy
  can be supplied at runtime via `--resource-min-memory-mb`; the default policy is the
  shared safe default (`min_available_memory_mb=768`, `max_swap_used_percent=90`,
  `max_disk_used_percent=85`, `min_disk_free_gb=8`, `min_inode_free_percent=10`).
- The module intentionally imports no `os.kill` / `signal` / `killpg` / `SIGKILL` /
  `SIGTERM` primitive (asserted by `test_budget_never_imports_killing_primitives`); it
  can only raise. It therefore cannot terminate Hermes, `/opt/bots/bitget-listener`,
  databases, or unrelated services.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. Unblocked research/engineering (resource safety) continues per
the cron mandate.
