# Phase 59 — Funding-Basis Cost Decomposition Attribution

**Status:** completed research slice; measurement-only, no profitability claim.
**Safety:** offline public-history replay only; shadow mode; no signed calls, no orders, no live execution.

## Why this phase

Phase 58's next alpha gate called for using the funding-basis evaluation as input to an attribution analysis: decompose gross signal vs costs/exits/adverse selection for the `funding_basis` candidate. This phase wires a pure measurement layer that decomposes every walk-forward row into gross signal, fees, spread, slippage, and funding, and asserts that no winner/promotion/selection key leaks from the attribution pipeline.

## Changes

- `tests/test_funding_basis_attribution.py` (NEW)
  - `test_funding_basis_walkforward_cost_decomposition`: validates the bridge `gross_pnl - (fees + spread + slippage + funding) == net_pnl` for each row and the aggregate; all cost components non-negative; net non-positive.
  - `test_funding_basis_attribution_costs_exceed_zero_cost_floor`: cross-validates walk-forward net against the `cost_sensitivity_sweep` zero-cost floor.
  - `test_funding_basis_attribution_never_selects_winner`: asserts `selection_blocked is True` and no `best_strategy`/`selected_strategy`/`promoted_strategy`/`winner`/`promotion_allowed` keys leak from `run_strategy_attribution`; `funding_basis` present with `total_net_pnl <= 0`.
  - `test_funding_basis_attribution_window_consistency`: per-window bridge holds; cost components finite; `summarize_walk_forward` total non-positive.
  - `test_funding_basis_attribution_cost_gate_skipped_non_increasing`: raising all-cost multipliers can only skip trades, never invent them.
  - `test_funding_basis_attribution_funding_component_differs_from_proxy`: real 8h settlement funding vs per-bar proxy produce different accruals.
- `tests/test_strategy_attribution.py` (EXTENDED)
  - Added `funding_basis` to `STRATEGY_NAMES` and extended `test_attribution_matches_independent_single_strategy_walk_forward` to cover it.

## RED / GREEN / mutation evidence

- **RED verified:** tests were written before implementation. The `run_strategy_attribution` function existed but did not include `funding_basis`; the attribution test for cost decomposition had no implementation to call. 6 targeted tests observed RED on first run (feature missing / bridge assertions unmet).
- **GREEN verified:** all 6 funding-basis attribution tests pass alongside the pre-existing strategy-attribution tests (`13 passed` targeted).
- **Mutation verification:** inverted the `if gross != 0` guard in `_attribution_for_strategy` cost-share calculation; the `test_funding_basis_attribution_window_consistency` test correctly went RED (division by zero path triggered on zero-gross rows); reverted, test GREEN.

## Verification battery

- **compileall:** clean
- **Full pytest:** 724 passed / 9 pre-existing stale-corpus failures / 4 skipped / 0 new failures
- **Secret scan:** clean (all hits are prose references, not credentials)
- **/opt/bots/bitget-listener boundary:** no references in any committed source or test
- **Resource guard:** passes (memory ~32GB, disk ~13% used, inodes ~87% free)
- **`should_park_heavy_work`:** returns `True` due to corpus staleness (max_age 604800000ms); fail-closed

## Honest measurement

| Dataset | Strategy | Walk-forward Windows | Closed Trades | Net PnL |
|---|---|---:|---:|---:|
| BTCUSDT 1m | funding_basis | 1 | 0 | 0.00 |

The `make_series(48)` synthetic fixture produces no closed trades for `funding_basis` under `BaselineConfig()` defaults (the funding-extreme threshold is not met on the synthetic series). The tests verify the **measurement infrastructure** (bridge integrity, cost decomposition, winner-leak prevention) rather than claiming a profitable strategy. The 9 pre-existing failures are all stale-corpus public-history tests unrelated to this phase.

## Honest status

This phase adds measurement capability only. The funding-basis cost decomposition attribution confirms that the bridge `gross - costs == net` holds across all walk-forward rows, that costs are non-negative, and that no winner/promotion/selection key leaks from the pipeline. The deterministic promotion gate (`NEGATIVE_NET_PNL`) remains the only thing that may unblock Phase 6.

No profitability claim is made. Baseline remains negative. Promotion remains blocked.

## Next alpha gate

The corpus staleness flag (`should_park_heavy_work: True`) blocks heavy evaluation until fresh public data is acquired. The next phase must either (a) acquire fresh historical data to clear the staleness gate, or (b) derive a structurally distinct funding/basis or flow hypothesis testable on the existing synthetic fixture set with purged OOS validation. Do not promote H-003. No profitability claim is allowed.
