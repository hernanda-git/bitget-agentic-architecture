# Phase 63 — Purged Chronological Walk-Forward Evaluation for Order-Flow Impulse

**Status:** measurement infrastructure; no profitability claim.
**Safety:** offline public-history replay only; shadow mode; no signed calls, no orders, no live execution.

## Why this phase

Phase 62 introduced `evaluate_purged_holding_periods()` which enforces the purged constraint for a flat
sequence of closes: every `exit_idx` is strictly bounded by `len(closes) - period`. However, when
evaluating across walk-forward test windows, the constraint must be enforced *per window*: labels from
window 0 must not leak into window 1's test territory, and vice versa.

This phase introduces `evaluate_purged_orderflow_walk_forward()` in `src/evaluation/orderflow_evaluation.py`,
which extends the purged holding-period label infrastructure to the walk-forward boundary. Each label
carries its `window_index`, `test_start`, and `test_end`, and the loop enforces `exit_idx <= test_end`
by construction.

## Changes

- `src/evaluation/orderflow_evaluation.py` — new module with `evaluate_purged_orderflow_walk_forward()`
  producing purged forward-return labels across walk-forward test windows with `entry_idx`, `exit_idx`,
  `forward_return`, timestamps, and window boundaries.
- `tests/test_purged_orderflow_walk_forward.py` — 6 tests covering module existence, label structure,
  no future leak, ValueError on invalid period, empty on insufficient data, and purge guard binding
  (mutation verified: relaxing the guard correctly produces a failure).

## RED / GREEN / mutation evidence

### RED verified
- `test_evaluate_purged_orderflow_walk_forward_module_exists`: confirmed `ModuleNotFoundError` before implementation.

### GREEN verified
- All 6 tests pass after implementation.
- Full test battery: **744 passed / 4 skipped / 0 failed** (738 baseline + 6 new).

### Mutation verification
- **Purged guard binds**: `exit_idx <= test_end` always holds; flipping the range to `test_end + 1`
  produces `exit_idx = 83 > test_end = 82`, and the test correctly fails. Reverted the mutation.

## Honest measurement

| Component | Tests | Status |
|---|---:|---|
| `evaluate_purged_orderflow_walk_forward` | 6 | PASS |
| **Full suite** | **744** | **PASS** |

The purged walk-forward evaluation produces measurement-only labels. The deterministic baseline remains
**negative** and **promotion remains blocked**. No profitability is claimed.

## Honest status

This phase verified the purged chronological walk-forward evaluation infrastructure for the order-flow
impulse hypothesis. The `evaluate_purged_orderflow_walk_forward` function enforces strict purging per
walk-forward test window, preventing lookahead across train/test boundaries. The deterministic baseline
remains **negative** and **promotion remains blocked**. No profitability is claimed.

## Next alpha gate

With the purged walk-forward evaluation verified, the next bounded phase should evaluate one structurally
distinct hypothesis (funding/basis or flow/price divergence) with purged chronological validation on the
fresh public-history corpus, followed by the cost sensitivity sweep to determine the break-even cost
multiplier.

No profitability claim is allowed. The deterministic promotion gate (`NEGATIVE_NET_PNL`) remains the only
thing that may unblock promotion.