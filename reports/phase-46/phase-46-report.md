# Phase 46 — First-class factor validation in the ontology (TDD + mutation-verified)

**Date:** 2026-08-30
**Author:** valarion (42990222+hernanda-git@users.noreply.github.com)
**Discipline:** TDD + mutation-verified, fail-closed, offline, no signed/order calls.

## Why this phase

Phase 45 made the factor *categories* canonical and bound them to the hypothesis
registry, but the concrete *factors* inside each category (`FACTOR_CATEGORIES`)
remained inert data: there was no fail-closed way to assert that a named factor
actually belongs to the category it claims. The directive sec. 3 mandates that the
ontology be continuously *extended, challenged, and pruned* — individual factors
must be challengeable, not just categories. This phase makes each concrete factor
first-class and validatable.

This is the bounded next step derived from the directive's standing §3 mandate:
Phase 45 itself deferred no concrete feature step and explicitly surfaced three
unrepresented categories (`macro_liquidity`, `flow_participation`,
`sentiment_attention`); per the continuation skill, when a hygiene phase defers no
concrete step we derive the bounded phase from the directive's §3/§5/§8 mandate.
Rather than invent a broad refactor, this phase adds the minimal behavior that lets
the factor space be challenged at the factor level.

## Changes

- **Extend `src/evaluation/factor_ontology.py`** with two fail-closed helpers:
  - `list_factors(category)` — returns the tuple of concrete factors enumerated
    under a canonical category; an unknown category raises `FactorOntologyError`
    (never a default/empty list).
  - `validate_factor(category, factor)` — returns `factor` only if it is a member
    of the given canonical category; an unknown category raises
    `FactorOntologyError`, and a factor that is listed under a *different*
    category is rejected (never coerced/aliased into the requested category).
- **Extend `tests/test_factor_ontology.py`** with 5 tests:
  - `test_list_factors_returns_members_of_a_known_category`
  - `test_list_factors_rejects_unknown_category`
  - `test_validate_factor_accepts_known_factor_in_its_category`
  - `test_validate_factor_rejects_factor_not_in_category`
  - `test_validate_factor_rejects_unknown_category`

## TDD cycle

- **RED:** added the 5 tests; import of `list_factors`/`validate_factor` failed
  (`ImportError`), confirming the feature is missing.
- **GREEN:** implemented both helpers minimally; the 11 tests in
  `tests/test_factor_ontology.py` pass (6 pre-existing + 5 new).
- **Mutation check (assertions genuinely bind):**
  - Bypassed the membership guard in `validate_factor` (`if False:`) →
    `test_validate_factor_rejects_factor_not_in_category` went **RED** (`DID NOT
    RAISE FactorOntologyError`). Restored. This proves the rejection assertion is
    not a tautology.
- **Full suite:** **638 passed, 4 skipped, 0 failed** (baseline 633 + 5 new),
  run with `-p no:cacheprovider` and `-q`.

## Verification battery

- `python -m compileall -q src scripts` → clean.
- `python -m pytest -q -p no:cacheprovider` → **638 passed, 4 skipped, 0 failed**.
- `python scripts/resource_guard.py` → `ok: true`, no violations (RAM ~27 GB free,
  disk 89% free inodes, swap 0% used).
- **Secret scan (contents):** 0 hits in changed paths (`src/evaluation/factor_ontology.py`,
  `tests/test_factor_ontology.py`). `.env` gitignored. No network, signed, or order
  calls.
- **`/opt/bots/bitget-listener` guard:** not referenced by any changed file; the
  pre-existing `test_boundary.py` / `test_safety_surface.py` still assert the
  project does NOT depend on it (unchanged).

## Honest status

The deterministic baseline remains **negative → promotion blocked** (no live/edge
claim). This phase is knowledge-base hardening only: it gives the directive sec. 3
factor space teeth at the factor level (a named factor can now be validated against
its declared category, fail-closed), supporting the standing "challenge/prune"
mandate. No profitability is claimed. The three unrepresented categories
(`macro_liquidity`, `flow_participation`, `sentiment_attention`) remain gaps —
surfaceable via `coverage_summary`, not hidden. The autonomous research loop is
healthy, green, and honest.

## Next candidate phase

A natural follow-on (bounded): wire `validate_factor` into `Hypothesis.validate()`
so a hypothesis must declare a *concrete factor* that is a member of its declared
*category* (not merely a known category) — closing the last gap between a hypothesis
claim and the auditable factor map. That is deferred deliberately to keep this phase
minimal and fail-closed.
