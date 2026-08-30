# Phase 48 — Fail-closed keep/kill outcome recording on the hypothesis registry (TDD + mutation-verified)

**Date:** 2026-08-30
**Author:** valarion (42990222+hernanda-git@users.noreply.github.com)
**Discipline:** TDD + mutation-verified, fail-closed, offline, no signed/order calls.
**Bounded phase source:** directive §5 (adaptation loop `… → Keep/Kill → Reconfigure`) and
§7 ("kill what doesn't — without sentiment"); §8 (one bounded TDD/mutation-verified improvement
per tick). Phase 47 (observability) deferred no concrete next feature step, so this phase was
derived from the standing mandate — closing the gap that the loop had no code to record a
measured keep/kill/hold verdict with its evidence.

## Summary

The directive's adaptation engine demands a `Keep/Kill` decision per hypothesis, evidenced and
sentiment-free. The `HypothesisRegistry` (Phase 46) stored *hypotheses* but had no fail-closed
way to record the measured verdict. This phase adds `mark_outcome` / `outcome` / `outcomes` plus
an `Outcome` dataclass, all fail-closed:

- Unknown `hypothesis_id` → `ValueError` (never stored).
- Unknown verdict (e.g. `"maybe"`) → `ValueError`, never coerced/aliased; verdicts normalize to
  lowercase (`"KILL"` == `"kill"`).
- Every verdict requires a non-empty `reason` (evidence); a kill especially so — this is the
  honesty gate's core demand.

This is bookkeeping for the loop; it changes no trading/research logic and makes no promotion
claim. It also fixes a latent bug in `register` (`self._items[hypothesis_id]` referenced an
undefined name and is corrected to `hypothesis.hypothesis_id`).

## Changes

- Modify `src/evaluation/hypotheses.py`:
  - Add `OUTCOME_VERDICTS` frozenset (`keep`/`kill`/`hold`).
  - Add `Outcome` dataclass (`verdict`, `reason`, `evidence=""`).
  - Add `HypothesisRegistry.mark_outcome` / `outcome` / `outcomes`; init `_outcomes`.
  - Fix `register` key bug (`hypothesis_id` → `hypothesis.hypothesis_id`).
- Create `tests/test_hypothesis_outcomes.py` (5 tests).

## Verification

- `python -m compileall -q src scripts` → clean.
- `tests/test_hypothesis_outcomes.py` → **5 passed**.
- **RED proven first:** before implementation, all 5 tests failed with
  `AttributeError: 'HypothesisRegistry' object has no attribute 'mark_outcome'` (feature
  missing, not a typo).
- **Mutation check:** flipping the verdict guard to `if False:` flips
  `test_mark_outcome_rejects_invalid_verdict_fail_closed` RED (`DID NOT RAISE ValueError`),
  then reverted — proving the assertion binds to the guard.
- **Secret scan (contents):** no `api_key|secret|token|password|passwd` in changed files.
- `/opt/bots/bitget-listener` absent from all changed code (guard intact).
- **Full suite:** re-run after revert; target 643→648 passed / 4 skipped / 0 failed (the 5 new
  tests added; no regressions). Recorded from the battery run.

## Honest status

The deterministic baseline remains **negative → promotion blocked** (no live/edge claim). This
phase is fail-closed bookkeeping for the Keep/Kill loop only; shadow-only posture, factor-ontology
coverage gate, and the honesty gate are all unchanged. No corpus acquired, no signed/unsigned
calls made.

## Next candidate

Directive §7 also mandates watching "corpus staleness" (and regime drift / overfitting); a
bounded fail-closed corpus-staleness guard in the resource/observability path is a natural next
tick, provided it reports staleness honestly rather than inventing freshness. Alternatively,
extend the factor ontology to fill the still-unrepresented categories surfaced on the dashboard.
