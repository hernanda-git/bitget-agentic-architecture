# Phase 51 — Wire `should_park_heavy_work` into the eval scripts (TDD + mutation-verified)

**Date:** 2026-09-01
**Author:** valarion (42990222+hernanda-git@users.noreply.github.com)
**Discipline:** TDD + mutation-verified, fail-closed, offline, no signed/order calls.
**Bounded phase source:** the "Next candidate" explicitly deferred by Phase 50 —
"Wire `evaluate_corpus_freshness` into the observability surface / heartbeat
status so a stale corpus is *visible* and can park heavy evaluation work
fail-closed (directive §7 + §11 automation contract)."
Phase 50 made the stale observation *visible*; this phase makes it *actionable*
by wiring `should_park_heavy_work()` into the two heavy-evaluation entrypoints
so they park fail-closed when the blessed corpus is stale.

## Summary

Phase 50 landed the fail-closed `evaluate_corpus_freshness` observation and the
`should_park_heavy_work(status)` predicate, but neither eval script consumed
the predicate. This phase wires `should_park_heavy_work()` into:

- `scripts/evaluate_candidate_family.py` — `main()` returns exit code 8
  (`CORPUS_STALE_PARKED`) when `should_park_heavy_work(assemble_status())` is
  true, before any candidate-family measurement begins.
- `scripts/evaluate_real_history.py` — same guard before the real-history replay loop.

No trading/research logic touched. No promotion claim. `data/history` is read-only and untouched.
The honesty gate is strengthened: a stale corpus cannot produce a questionable family-wise measurement.

## Changes

- `scripts/heartbeat_status.py`: add `should_park_heavy_work(status)` —
  returns `True` when `corpus_freshness.stale` is true, when the status is `None`,
  malformed, or missing the key; fail-closed by design.
- `tests/test_heartbeat_status.py`: 4 new tests (should_park_returns_true/false/
  unavailable/fail_closed_on_malformed_status).
- `scripts/evaluate_candidate_family.py`: import `assemble_status`,
  `should_park_heavy_work`; early-return exit 8 with `CORPUS_STALE_PARKED`.
- `scripts/evaluate_real_history.py`: same guard before the replay loop.
- `tests/test_evaluate_candidate_family.py`: 1 new test (parks_when_corpus_stale).

## Verification

- `python -m compileall -q src scripts` → clean (COMPILE_OK).
- **RED proven first:** the 5 new tests failed before implementation (ImportError
  on missing `should_park_heavy_work`; behavioral gaps, not typos).
- **GREEN:** targeted tests → 5 passed.
- **Full suite:** baseline 655 passed / 4 skipped / 0 failed → **670 passed / 4 skipped / 0 failed** (+15 new).
- **Mutation checks (all reverted after confirming RED):**
  1. flip stale guard direction → test_should_park_returns_true_when_corpus_stale RED.
  2. fail-closed on None → test_should_park_fail_closed_on_malformed_status RED.
  3. bypass dict-type guard → test_should_park_fail_closed_on_malformed_status RED.
- **Resource guard:** ok true, violations empty.
- **Secret scan (contents):** only prose matches; no credential.
- `/opt/bots/bitget-listener`: pre-existing guard-reference lines only.

## Honest status

Deterministic baseline remains negative → promotion blocked. Shadow-only posture,
factor-ontology coverage gate, and honesty gate unchanged. No corpus acquired this
tick; no signed or unsigned order calls made.

## Next candidate

Extend the factor ontology to fill still-unrepresented categories surfaced on the
dashboard (directive §3), or wire `should_park_heavy_work` into the cron entrypoint.
