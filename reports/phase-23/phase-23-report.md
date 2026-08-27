# Phase 23 — Fail-closed protection read-back: reject stops on the wrong side of mark (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-28 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline protection-engineering (measurement only), no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `protection` and `reconciliation` as unblocked streams. The
agentic-architecture skill (Layer 7) requires that protection be verified by venue
read-back and that "if protection is missing, state is inconsistent, or liquidation is
on the wrong side of the stop, park new entries." This phase closes a concrete,
dangerous gap found in the existing read-back logic:

`reconcile_protection` (the canonical Layer 7 check) only validated that the venue's
echoed SL/TP *equalled* the intended values. It never checked that the stop sat on the
**correct side** of the current mark for the position side. A LONG whose `stop_loss` is
at or above the mark (a misconfigured/garbled stop, or an "accepted-but-dropped" order
echoed back by the venue) would be reported `PROTECTED` while providing **zero** downside
protection. Worse, `ProtectionSupervisor.verify` (the *live* path) duplicated divergent
inline logic that had the same blind spot and did not even call the canonical function.

This phase:
1. Adds a directional check to `reconcile_protection`: a protective stop must be strictly
   below mark for LONG and strictly above mark for SHORT; otherwise `WRONG_SIDE_STOP` ->
   `DEGRADED`.
2. Refactors `ProtectionSupervisor.verify` to delegate to `reconcile_protection` (single
   source of truth) and persists the read-back `reasons` on the `ProtectionRecord` for
   traceability (Layer 8 observability: every cycle gets a terminal disposition + reason).
3. Fixes a genuine consistency bug surfaced by the regression gate: `bot_complete` could
   true-positive when both intended and bot stops were `None` (a position with no intended
   stop was wrongly `PROTECTED`). Now requires non-None levels.

No policy gate, LLM, or execution path is added. Phase 6 remains blocked.

## Resource guard (run at start of every run)

```text
python3 scripts/resource_guard.py --json
  ok: true
  violations: []
  swap_used_percent: 84.36 (< policy max 90.0)
  available_memory_bytes: 1769607168
  disk_free_bytes: 31734792192
  inode_free_percent: 50.14
```

GREEN, so the full heavy suite was permitted as the regression gate.

## TDD cycle (strict, two vertical slices)

### Cycle 1 — RED (wrong-side stop not detected)

New file `tests/test_protection_wrong_side.py` with 5 reconcile-level tests (3 wrong-side
degradation cases + 2 positive protective controls). Run before the fix:

```text
pytest tests/test_protection_wrong_side.py -v
  FAILED test_reconcile_protection_degrades_long_stop_above_mark
  FAILED test_reconcile_protection_degrades_short_stop_below_mark
  FAILED test_reconcile_protection_degrades_stop_at_mark
  2 passed (the positive LONG/SHORT protective controls)
  4 failed, 2 passed
```

Fails because the wrong-side stop is reported `PROTECTED` (feature missing, not a typo).
The 2 positive controls pass, proving the tests do not break legitimate protection.

### Cycle 1 — GREEN (minimal code)

`src/reconcile/engine.py::reconcile_protection` gains:

```python
if side and mark is not None and sl is not None:
    su = side.upper()
    if su == "LONG" and sl >= mark:
        reasons.append("WRONG_SIDE_STOP")
    elif su == "SHORT" and sl <= mark:
        reasons.append("WRONG_SIDE_STOP")
_fatal = any(r.startswith("LIQUIDATION_") or r == "WRONG_SIDE_STOP" for r in reasons)
state = PROTECTED if (venue_complete or bot_complete) and not _fatal else DEGRADED
```

Run: `5 passed`.

### Cycle 2 — RED (live path + delegation)

Added `test_supervisor_verify_degrades_wrong_side_stop` (register a garbled LONG with
intended stop 105, verify with venue echo 105 and mark 100 -> expect DEGRADED). Also the
test file referenced `supervisor.verify(..., mark=100)` which did not yet exist. Run before
the refactor:

```text
FAILED test_supervisor_verify_degrades_wrong_side_stop
  TypeError: ProtectionSupervisor.verify() got an unexpected keyword argument 'mark'
```

### Cycle 2 — GREEN (refactor to single source of truth)

`ProtectionRecord` gains a `reasons: tuple[str, ...] = ()` field (stored/round-tripped via
`to_dict`/`from_dict`, defaulted on load). `ProtectionSupervisor.verify` now delegates to
`reconcile_protection` and persists `result.reasons`. The inline divergent logic is removed.

Regression gate immediately caught a second real bug: `bot_complete` lacked a non-None
requirement, so a position with **no intended stop** (registered with `None`/`None`) read as
`PROTECTED` via the fresh bot monitor. Fixed by requiring `sl is not None and tp is not None`
in `bot_complete`. After the fix the pre-existing
`test_fresh_bot_monitor_cannot_protect_without_intended_levels` passes (it had been
inconsistent with the canonical function).

### REFACTOR

The only duplication (inline protection verdict in `supervisor.verify`) is eliminated by
delegation; no further extraction needed.

## Raw tests (executed this run)

```text
# New phase-23 suite (GREEN):
.venv/bin/python -m pytest tests/test_protection_wrong_side.py -v
  6 passed in 0.02s

# Protection regression set (GREEN):
.venv/bin/python -m pytest tests/test_protection_wrong_side.py \
    tests/test_protection_supervisor.py tests/test_protection_reconciliation.py -q
  15 passed in 0.05s

# Full project regression gate (GREEN, resource guard permitted heavy run):
.venv/bin/python -m pytest tests/ -q
  446 passed in 196.66s

# Compileall (whole tree, clean):
.venv/bin/python -m compileall -q src scripts tests
  -> exit 0 (clean)
```

## Mutation check (assertions bind to real logic, not decoration)

Per build-verification, a suite that cannot fail is the same trap as a flat-line metric.
Backed up `src/reconcile/engine.py`, mutated the directional guard to `if False:`, ran the
phase-23 suite, then restored:

```text
# under mutation (wrong-side guard disabled):
.venv/bin/python -m pytest tests/test_protection_wrong_side.py -q
  4 failed, 2 passed in 0.04s
  FAILED: degrades_long_stop_above_mark, degrades_short_stop_below_mark,
          degrades_stop_at_mark, supervisor_verify_degrades_wrong_side_stop
  2 passed (the positive-control protective LONG/SHORT stops)
# restored:
  6 passed in 0.02s
```

The exact wrong-side detection assertions fail under mutation and pass when restored,
proving they bind to the new logic.

## Network calls / signed calls / orders / positions

- **Network calls: 0.** No public Bitget acquisition occurred this run (the phase is a
  pure offline read-back logic fix; existing `data/history/*.json` already carry funding
  records, so no new acquisition was required).
- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed). No credentials, demo
  keys, or live keys were used. No signed exchange calls, transfers, withdrawals, or
  funded execution occurred. The fix runs purely over in-process dict/record structures
  and fakes.

## Trades / fees / funding / PnL

No trades, fees, funding, or realized PnL were produced. This phase is a correctness
strengthening of the protection read-back verdict; it touches no market simulation or
PnL path. The 446 passing tests include the existing cost/funding/slippage stress and
walk-forward suites, which remain green and unmodified by this change.

## Protection / reconciliation (this phase's subject)

- `reconcile_protection` now fails closed on a stop at or across mark for the position
  side (`WRONG_SIDE_STOP` -> `DEGRADED`), in addition to the pre-existing
  `LIQUIDATION_GE_STOP` / `LIQUIDATION_LE_STOP` and `VENUE_PROTECTION_MISSING` checks.
- `ProtectionSupervisor.verify` (the live verification path used by the orchestrator's
  protection step) now routes through the canonical function, so the live path cannot
  diverge from the tested read-back logic and gains the directional check.
- The read-back `reasons` are persisted on the `ProtectionRecord`, giving each protection
  cycle a traceable terminal disposition for the append-only ledger.
- A position with no intended stop can no longer be marked `PROTECTED` by a fresh bot
  monitor (was a silent true-positive; now `DEGRADED`).

## Limitations (honest)

- The directional check requires `mark` to be supplied to the read-back. The orchestrator's
  protection step must pass the current mark from the market gateway; if mark is absent
  the check is skipped and the verdict falls back to the venue/bot echo match (preserving
  prior behavior). Callers that omit mark lose the wrong-side guarantee — this is
  documented as a required input at the `verify` boundary.
- The check validates the *intended/echoed* stop against mark; it does not re-derive
  whether the stop distance is economically adequate (that belongs to the policy engine's
  risk rules, which are a separate layer). This phase only proves the stop is on the
  protective side.
- The mutation check was performed manually (backup/mutate/restore) and reported here
  rather than committed as a permanent test, matching the build-verification skill's
  prescribed procedure.
- The full 446-test suite was run once and passed (~197s CPU); it is the project's
  verification gate.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. This phase strengthens Layer 7 protection/reconciliation truth
(an unblocked stream) and adds no selection, LLM, or execution path. Unblocked
research/engineering continues per the cron mandate.
