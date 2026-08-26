# Phase-10: realistic combined cost/funding/slippage stress (fail-closed)

**Status:** DONE_LIMITATIONS — measurement only, selection blocked.
**Generated (Asia/Jakarta):** see `summary.json` `generated_at_utc`.
**Mode:** public unauthenticated stored history, FakeExchange only. No credentials, no signed calls, no orders.

## What changed
- Added `src/evaluation/stress.run_combined_stress` — a realistic *simultaneous* adverse-cost stress that raises fee, funding, and slippage multipliers **together** (1.5x / 2.0x / 1.5x by default), modeling a worst-case cost environment where every execution cost moves against the strategy at once. This is more realistic than the isolated stress-matrix dimensions, which raise only one cost at a time.
- Wired it into the durable `scripts/evaluate_real_history.py` pipeline (`combined_stress` field).
- Added `scripts/run_combined_stress_report.py` (network-free, secret-free, re-runnable) and `tests/test_combined_stress.py` (strict TDD).

## TDD evidence
- RED: `tests/test_combined_stress.py` failed at collection with `ImportError: cannot import name 'run_combined_stress' from 'src.evaluation.stress'` before any implementation existed.
- GREEN: implemented minimal `run_combined_stress`; 3 unit tests pass.
- Mutation check: forcing `promotion_allowed: True` turned exactly 2 of 4 tests red (`test_combined_stress_reports_worst_case_costs_and_is_blocked`, `test_combined_stress_pipeline_invariant_on_real_dataset`); reverted to green. The assertions bind to real behavior, not constants.
- Full suite: **333 passed** (was 329); `python3 -m compileall` clean. No regressions.

## Raw evidence (this run)
- network_calls: 0 (stored datasets, no fetch)
- signed_calls: 0
- orders: 0
- positions: 0
- trades (closed, baseline / combined): BTCUSDT_1m 45 / 45, BTCUSDT_5m 245 / 245, ETHUSDT_1m 63 / 63, ETHUSDT_5m 310 / 310
- fees/funding/slippage/spread: see `summary.json` per-dataset `baseline` and `combined_stress`
- PnL (net, baseline / combined): BTCUSDT_1m -6872.31 / -8444.54, BTCUSDT_5m -21917.09 / -22340.19, ETHUSDT_1m -299.21 / -360.84, ETHUSDT_5m -747.64 / -903.28

## Fail-closed invariant (the point of the work)
For every stored dataset the combined stress MUST:
1. never add trades versus baseline (`combined.closed_trades <= baseline.closed_trades`) — PASS all 4
2. keep `promotion_allowed=False` / `promotion_status="BLOCKED"` — PASS all 4
3. leave the walk-forward robustness gate `selection_blocked=True` — PASS all 4
4. leave `expectancy_positive_with_ci=False` — PASS all 4

`invariant_all_pass=True`. Realistic adverse cost stress makes the already-NEGATIVE baseline **more** negative in every dataset; no profitability was manufactured.

## Protection / reconciliation
- N/A: evaluation mode, FakeExchange only. No venue protection attached, no venue read-back, no reconciliation possible here.

## Promotion gate
- deterministic_baseline: NEGATIVE across all four 2000-candle public-history datasets
- phase6_bounded_llm_selection: BLOCKED (negative baseline)
- selection_blocked: True throughout

## Limitations
- Stored public history (2000 candles/symbol/granularity) is a fixed historical snapshot; no live stream.
- Historical bid/ask was unavailable from the public API; spread remains an explicit assumed half-spread (0.5 bps), never an observed quote claim.
- Evaluation uses FakeExchange only; no signed/demo/testnet execution occurred, so no venue reconciliation or protection read-back is possible.
- The combined stress is measurement only and never changes the deterministic promotion gate (still NEGATIVE_NET_PNL).
- Public unauthenticated history does not establish live venue reconciliation; the negative baseline is a deterministic cost-inclusive replay result, not a live trading outcome.
- No strategy was selected, ranked, or promoted; selection_blocked remains True throughout.
