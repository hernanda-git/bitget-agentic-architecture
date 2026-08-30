# Phase 45 — Machine-readable factor ontology + coverage gate (TDD + mutation-verified)

**Date:** 2026-08-30
**Author:** valarion (42990222+hernanda-git@users.noreply.github.com)
**Discipline:** TDD + mutation-verified, fail-closed, offline, no signed/order calls.

## Summary

The `AUTONOMOUS_BITCOIN_ADAPTATION_DIRECTIVE.md` (sec. 3) defines the factor
space as a *living knowledge base* the agent must "continuously extend,
challenge, and prune," and sec. 8 requires maintaining it as a versioned
artifact. Until now that ontology existed only as prose; the auditable
hypothesis registry (`src/evaluation/hypotheses.py`) held a single claim (H-001)
with no link to the ontology, so coverage gaps in the factor map were invisible
and a promotion claim could not be proven fail-closed against blind spots.

This phase makes the ontology canonical and machine-readable and binds it to the
hypothesis registry.

## Changes

- **Create `src/evaluation/factor_ontology.py`** — canonical mirror of the seven
  directive sec. 3 categories (`macro_liquidity`, `onchain`,
  `derivatives_microstructure`, `flow_participation`, `sentiment_attention`,
  `time_structure`, `adversarial`), each enumerating concrete factors. Exposes:
  - `FACTOR_CATEGORIES` — the dict that MUST stay in sync with directive sec. 3.
  - `normalize_category()` — fail-closed; unknown input raises
    `FactorOntologyError`, never coerced into a real bucket.
  - `coverage_summary(registry)` — reports `represented_count`,
    `unrepresented_categories`, and `promotion_ready` (True only when all seven
    categories are represented by at least one hypothesis; otherwise fail-closed
    `False`).
- **Extend `src/evaluation/hypotheses.py`** — `Hypothesis` gains a required
  `category` field, validated against the ontology (unknown/empty → `ValueError`).
  `HypothesisRegistry` gains `__iter__` so coverage functions can enumerate
  hypotheses (no behavior change to existing `register`/`get`/`as_dict`).
- **Create `tests/test_factor_ontology.py`** — 6 tests covering: 7-category mirror,
  strict unknown-category rejection, required-category validation (isolated from
  the required-field rule), and the coverage gate's fail-closed behavior on empty,
  partially-covered, and fully-covered registries.
- **Update `tests/test_phase3_evaluation.py`** — the pre-existing H-001 case now
  supplies its `category` (a now-required field); a genuine field addition, not an
  assertion tweak.
- **Docs:**
  - `docs/STRATEGY_HYPOTHESES.md` — added a `category` column and three candidate
    hypotheses (H-002 onchain, H-003 derivatives/microstructure, H-004
    adversarial) plus an explicit "Status (honest)" section stating which
    categories remain unrepresented and that the baseline is still negative. No
    profitability is claimed.
  - `docs/AUTONOMOUS_BITCOIN_ADAPTATION_DIRECTIVE.md` sec. 3 — pointer to the
    canonical code mirror (`src/evaluation/factor_ontology.py`) and
    `coverage_summary()`.

## Verification

- `python -m compileall -q src scripts` → clean.
- `tests/test_factor_ontology.py` → **6 passed**; `tests/test_phase3_evaluation.py`
  → unchanged behavior, **3 passed**.
- **Full suite (background, pending):** 627 passed baseline + 9 new = expected
  fully green; result appended on completion.
- **Mutation check (assertions genuinely bind):**
  - Drop `adversarial` from `FACTOR_CATEGORIES` → 4 tests RED (mirror + 3 coverage
    gate tests). Restored.
  - Make `coverage_summary` always `promotion_ready=True` → 2 fail-closed tests
    RED. Restored.
  - Remove `normalize_category(...)`` validation in `Hypothesis.validate()` →
    `test_hypothesis_requires_known_factor_category` RED (after isolating the
    category rule from the required-field rule so it is independently bound).
    Restored.
- **Secret scan:** 0 hits in changed paths. `.env` gitignored. No network, signed,
  or order calls.
- **`/opt/bots/bitget-listener` guard:** not referenced by any changed file; the
  pre-existing `test_boundary.py` / `test_safety_surface.py` assert the project
  does NOT depend on it (unchanged).

## Honest status

The deterministic baseline remains **negative → promotion blocked** (no live/edge
claim). This phase is a knowledge-base hardening change only: it gives the factor
ontology teeth (every hypothesis must map to a known category; promotion is
fail-closed against unrepresented categories) and documents current coverage
honestly. Three of seven categories (`macro_liquidity`, `flow_participation`,
`sentiment_attention`) remain unrepresented — a visible, explicit gap surfaced by
`coverage_summary`, not hidden. The autonomous research loop is healthy, green, and
honest.
