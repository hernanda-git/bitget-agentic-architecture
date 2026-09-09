# Phase 64 — Purged Chronological Walk-Forward Evaluation for Funding-Basis (H-003)

**Status:** measurement infrastructure; no profitability claim.
**Safety:** offline public-history replay only; shadow mode; no signed calls, no orders, no live execution.

## Why this phase

Phase 63 introduced `evaluate_purged_orderflow_walk_forward()` for the order-flow impulse
candidate (H-003 in the orderflow_impulse module), extending the purged holding-period label
infrastructure to the walk-forward boundary. The funding-basis mean-reversion hypothesis
(H-003, `src/strategies/funding_basis.py`) is a structurally distinct strategy in the
`derivatives_microstructure` factor category with identical need for purged walk-forward
label evaluation. This phase mirrors the Phase 63 pattern for funding-basis.

## Changes

- `src/evaluation/funding_basis_evaluation.py` — new module with `evaluate_purged_funding_basis_walk_forward()`
  producing purged forward-return labels across walk-forward test windows for the
  funding-basis hypothesis, with strict per-window purging (every `exit_idx <= test_end`).
- `tests/test_purged_funding_basis_walk_forward.py` — 6 tests covering module existence,
  label structure, no future leak, ValueError on invalid period, empty on insufficient
  data, and purge guard binding (mutation verified).

## RED / GREEN / mutation evidence

### RED verified
- `test_evaluate_purged_funding_basis_module_exists`: confirmed `ModuleNotFoundError` before implementation.

### GREEN verified
- All 6 tests pass after implementation.
- Full test battery: **750 passed / 4 skipped / 0 failed** (744 baseline + 6 new).

### Mutation verification
- **Purge guard binds**: `exit_idx <= test_end` always holds; flipping the range to
  `range(test_start, test_end + 1)` produces `exit_idx = 83 > test_end = 82`, and the
  test correctly fails. Reverted the mutation.

## Honest measurement

| Component | Tests | Status |
|---|---:|---|
| `evaluate_purged_funding_basis_walk_forward` | 6 | PASS |
| **Full suite** | **750** | **PASS** |

The purged walk-forward evaluation produces measurement-only labels for the funding-basis
hypothesis. The deterministic baseline remains **negative** and **promotion remains blocked**.
No profitability is claimed.

## Honest status

This phase verified the purged chronological walk-forward evaluation infrastructure for the
funding-basis mean-reversion hypothesis (H-003, derivatives_microstructure). The
`evaluate_purged_funding_basis_walk_forward` function enforces strict purging per walk-forward
test window, preventing lookahead across train/test boundaries — the same pattern established
in Phase 63 for order-flow impulse. The deterministic baseline remains **negative** and
**promotion remains blocked**. No profitability is claimed.

## Next alpha gate

With the purged walk-forward evaluation verified for both order-flow impulse and funding-basis,
the next bounded phase should evaluate cost sensitivity break-even for the funding-basis
hypothesis specifically, or one structurally distinct hypothesis (flow/price divergence or
adversarial) with purged chronological validation on the fresh public-history corpus.

No profitability claim is allowed. The deterministic promotion gate (`NEGATIVE_NET_PNL`) remains
the only thing that may unblock promotion.
