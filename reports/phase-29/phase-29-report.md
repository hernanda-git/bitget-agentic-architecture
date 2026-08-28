# Phase 29 — Strategy attribution by market regime (TDD + build-verified)

**Date:** autonomous cron run (Asia/Jakarta timezone)
**Mode:** offline, no network, no credentials, no orders, no signed calls.
**Scope:** strengthen strategy attribution so the *honest-edge* question is answerable: is a strategy's positive aggregate carried by a single regime (fragile) or robust across regimes?

## What was added

`src/evaluation/attribution.attribute_performance_by_regime(strategy_returns, regime_labels, ...)`
slices the SAME aligned per-step return stream by an externally supplied
`regime_labels` series (one label per shared timestep, produced by
`src.strategies.regime.classify_regime` in the real pipeline) and reports,
fail-closed and descriptively:

* per-regime equal-weight blend expectancy + bootstrap CI + sample size
* per-strategy / per-regime expectancy matrix
* edge concentration: which regime carries the most `|net|` and its share

The family-level `attribute_performance` only decomposes by strategy *family* and
cannot see regime concentration; a lone lucky regime can launder a spurious edge
past the cross-sectional dispersion check. This layer closes that blind spot.

It never emits a winner / promotion / selection flag and `selection_blocked` is
always `True`, so it cannot change the deterministic Phase 6 promotion gate
(currently negative). `find_overclaims` from `report_honesty` is asserted clean.

## TDD cycle

RED first: `tests/test_regime_attribution.py` was written before the function
existed; collection failed with `ModuleNotFoundError: No module named
'src.evaluation.attribution'` ... actually the function path (the tests import
`attribute_performance_by_regime` which did not exist) => `AttributeError` on the
missing symbol. Confirmed RED for the right reason (feature missing).

GREEN: added the function with strict input validation (>= 2 strategies, aligned
lengths, finite returns) and a bootstrap CI. Minimal, no extra behavior.

REFACTOR: none required.

## Honest findings

* The blend per regime equals the cross-strategy mean of returns at that regime's
  steps — verified exactly in `test_attribution_by_regime_decomposes_per_regime_expectancy`.
* Edge concentration correctly identifies the regime with the largest `|net|`
  contribution and reports its share (e.g. `RANGING` dominant at 0.596 in the
  constructed example), exposing fragile single-regime edges.
* A `DATA_DEGRADED` (or any sparse) regime is reported, not dropped or
  overclaimed — important for dashboard truthfulness under data outages.

## Verification

* 8 new unit tests pass (`tests/test_regime_attribution.py`).
* `find_overclaims` returns `[]` on every report (no promotion/winner overclaim).
* `compileall` clean on the changed module.
* No network, no signed calls, no orders, no credentials touched.

## Limitations (explicit, not hidden)

* This module consumes regime labels as an injected argument; it does NOT itself
  classify regimes. The bridge that feeds real `classify_regime` labels into it
  is delivered separately (phase-30) so the two layers stay independently testable.
* Bootstrap CIs use default `min_samples=30`; small regimes yield wider intervals
  (correctly, not overconfidently).
* Descriptive only: does not, and cannot, unblock Phase 6 promotion.
