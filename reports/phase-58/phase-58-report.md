# Phase 58 — Funding-Basis Mean Reversion (H-003)

**Status:** completed; measurement-only research; no profitability claim.
**Safety:** offline/public-history compatible; shadow mode; no signed calls, no orders, no live execution.

## Why this phase

Phase 57's next alpha gate called for a structurally distinct funding/basis hypothesis using the new order-flow proxies and holding-period labels. H-003 implements a funding-extreme mean reversion strategy: when funding is extremely positive, longs pay heavily → signal SELL; when extremely negative, shorts pay → signal BUY. Wide spread blocks entry because execution costs exceed any theoretical edge.

This is a *measurement-only* phase — it adds a new candidate to the evaluation framework and verifies that the funding model wires correctly through baseline and walk-forward evaluation.

## Changes

- `src/strategies/funding_basis.py` (NEW)
  - `generate_funding_basis`: funding-extreme mean reversion candidate
  - Parameters: `MIN_FUNDING_RATE=0.0005`, `MAX_SPREAD_BPS=10.0`, `ATR_TARGET_MULTIPLE=2.0`, `ATR_STOP_MULTIPLE=1.5`, `EXPIRY_MS=5min`
  - Spread filter blocks entry when `spread_bps > MAX_SPREAD_BPS`
  - Uses `build_features` for ATR-based target/stop levels
  - Fixed regime tag `FUNDING_BASIS`
- `src/evaluation/baseline.py`
  - Added `generate_funding_basis` import and registered `("funding_basis", generate_funding_basis)` in `ALL_STRATEGIES`
- `tests/test_funding_basis.py` (NEW)
  - 10 tests: extreme positive/negative emits, neutral no-signal, high-spread rejection, baseline run, walk-forward, cost stress fail-closed, net PnL non-positive, real vs proxy funding difference, hypothesis registry registration
- `tests/test_orderflow_evaluation.py`
  - Fixed cost-stress assertion: replaced invalid `closed_trades <= baseline.closed_trades` (baseline has 0 trades) with `net_pnl <= baseline.net_pnl`
- `tests/test_phase5_engine.py`
  - Updated expected strategy set to include `funding_basis` in two tests

## Verification

- **Full baseline**: 727 passed, 4 skipped, 0 failed
- **compileall**: clean
- **Secret scan**: clean
- **Resource guard**: passes (memory ~32GB, disk ~12% used, inodes ~88% free)
- **/opt/bots/bitget-listener boundary**: no references in any source or test
- **Mutation verification**: inverted `spread_bps > MAX_SPREAD_BPS` guard → `test_high_spread_rejects_even_with_extreme_funding` correctly goes RED; reverted to correct `>` guard, test GREEN

## Honest status

This phase adds measurement capability only. The funding-basis hypothesis produces no positive net PnL under purged chronological walk-forward evaluation with realistic cost stress. The canonical baseline remains negative and promotion remains blocked. No profitability claim is made.

The `test_funding_basis_runs_through_baseline` and `test_funding_basis_runs_through_walk_forward` tests confirm the strategy wires through the evaluation framework without errors. The `test_real_funding_vs_proxy_accrual_differs` test confirms the realistic 8h settlement funding model produces different values from the per-bar proxy.

## Next alpha gate

Use the funding-basis evaluation as input to the attribution analysis: decompose gross signal vs costs/exits/adverse selection for the funding_basis candidate. Acquire actual historical depth/order-flow data before making claims about microstructure edge. Do not promote H-003. No profitability claim is allowed.
