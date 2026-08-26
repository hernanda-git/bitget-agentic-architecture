# Phase 11 - Walk-forward multiple-testing correction (measurement only)

**Run (Asia/Jakarta, UTC+7):** autonomous cron session
**Git identity:** `𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟` <42990222+hernanda-git@users.noreply.github.com>
**Skill stack:** test-driven-development (RED-GREEN-REFACTOR), build-verification, fully-agentic-trading-architecture, github-safe-publish

## Context

Phase 6 (bounded LLM selection) stays BLOCKED because the deterministic baseline is
negative. This run continues unblocked research/engineering on walk-forward evaluation
(cron focus #2: strengthen walk-forward evaluation against the family-wise error
problem). The previous session left an in-progress TDD cycle: a test file
`tests/test_walk_forward_multiple_testing.py` was written first (RED) and the
`n_tests` Bonferroni parameter was added to `gate_walk_forward_robustness`, but the
`family_wise_robustness` aggregation function it imports was never implemented, so the
whole module failed collection with `ImportError`.

## TDD cycle executed

### RED (observed first)
`pytest tests/test_walk_forward_multiple_testing.py -q` -> collection error:
`ImportError: cannot import name 'family_wise_robustness' from 'src.evaluation.baseline'`.
Confirmed the test was written before the code (correct failing-first state).

### GREEN (minimal implementation)
Added `family_wise_robustness(tests, *, alpha=0.05)` to `src/evaluation/baseline.py`.
It reuses the existing Bonferroni semantics inside `gate_walk_forward_robustness`:
- naive verdict: `gate(..., n_tests=1, confidence=1-alpha)` -> per-test level `1-alpha`
- corrected verdict: `gate(..., n_tests=len(tests), confidence=1-alpha)` -> per-test
  level `1 - alpha/len(tests)`, the textbook Bonferroni adjustment.

A candidate is "positive" when its gate returns `expectancy_positive_with_ci`. The
aggregator reports `uncorrected_positives`, `corrected_positives`, `any_*` flags, and
always `selection_blocked=True`. It never emits `promoted`/`selected`/`winner` keys.

### Test-fixture correction (honest, not result-tuning)
`test_family_wise_requires_consensus_across_strategies_flag` originally used
`lucky_pnls = [31.0]*100 + [-21.0]*100` to show 3 lucky windows flipped to 0 by the
k=8 correction. Measurement showed the k=8 (~99.4%) CI lower bound for that distribution
is still +0.58, so the correction genuinely does NOT flip it (the fixture sat on the
statistical boundary). The code correctly implements Bonferroni; the fixture was wrong.
Fixed the fixture to `[40.0]*100 + [-30.0]*100`, which is clearly positive under naive
95% CI (lower +0.45) and clearly negative under the family-wise CI (lower -0.95),
preserving the test's intent without faking a verdict.

### Verification
- `pytest tests/test_walk_forward_multiple_testing.py -v` -> **8 passed**
- `pytest tests/ -q` -> **341 passed, 0 failed** (no regressions)
- `python -m compileall -q src` -> clean (exit 0)
- content-level secret scan of tracked + untracked text -> **0 hits**; `.env` ignored

## Raw evidence ledger for this work unit

| field | value |
|-------|-------|
| raw tests | 8 new in `tests/test_walk_forward_multiple_testing.py`; full suite 341 passed |
| network calls | 0 (pure offline statistical evaluation) |
| signed calls | 0 |
| orders | 0 |
| positions | 0 |
| trades | 0 (no execution path exercised) |
| fees | 0 |
| funding | 0 |
| PnL | N/A (edge-significance measurement, never a PnL claim) |
| protection | N/A |
| reconciliation | N/A |
| deterministic baseline gate | still NEGATIVE_NET_PNL -> Phase 6 selection remains BLOCKED |

## What the correction does (honest summary)

- Without correction, scanning many candidate edges (3 strategies x 4 datasets = 12,
  more with cost/coverage variants) lets a single spuriously-positive window read as
  proven positive expectancy.
- The Bonferroni aggregator reports how many candidates survive naive vs corrected
  scanning. A lone lucky survivor among negatives is reported as `uncorrected_positives`
  while `corrected_positives` drops to 0.
- A genuinely strong, low-variance edge still survives correction (`any_corrected_positive=True`).
- This gate is MEASUREMENT ONLY. It never changes `NEGATIVE_NET_PNL` and never promotes.

## Limitations

- Bonferroni is conservative (controls family-wise error rate but can over-reject true
  edges when many candidates exist). No selection is performed, so over-rejection has no
  go-live consequence here.
- Bootstrap CIs depend on `seed` (default 0) and `samples` (2000); the verdict is
  deterministic for a fixed seed but the boundary flip is seed-sensitive at the margin.
- This is statistical hygiene over already-negative walk-forward results; it does not
  create positive edge and does not unblock Phase 6.

## Deliverables

- `src/evaluation/baseline.py`: added `family_wise_robustness` + `n_tests` Bonferroni
  parameter on `gate_walk_forward_robustness`.
- `tests/test_walk_forward_multiple_testing.py`: 8 tests (written first, RED, then GREEN).
- Full suite green, compileall clean, secret scan clean.

## Phase gate status

- Phase 6 (LLM selection): **BLOCKED** (negative deterministic baseline, unchanged).
- Unblocked walk-forward strengthening: **DONE** for this cycle; committed and pushed.
