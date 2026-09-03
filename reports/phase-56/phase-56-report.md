# Phase 56 — Correct OOS confidence accounting and test volume impulse

**Status:** completed; candidate inconclusive/falsified for current corpus; promotion blocked.
**Safety:** offline public-history replay only; no signed calls, no orders, no live execution.

## Why this phase

An independent audit found that `evaluate_candidate_family()` passed full-replay
`baseline.trade_pnls` into the walk-forward robustness gate. Those trades can include
train/context observations, contaminating the OOS trade-level confidence interval.
That had to be corrected before trusting any positive candidate result.

## Changes

- `src/evaluation/baseline.py`: robustness gates now receive only the concatenated
  `trade_pnls` from walk-forward rows, i.e. trades closed inside OOS test windows.
- `tests/test_oos_trade_accounting.py`: contradictory train losses versus positive OOS
  trades prove the gate consumes only OOS PnLs.
- `src/strategies/volume_confirmed_impulse.py`: one fixed, pre-registered candidate
  using causal 3-bar impulse, volume z-score >= 1.5, ATR exits, symmetric direction,
  and cost rejection. No parameter sweep.
- `tests/test_volume_confirmed_impulse.py`: long/short, volume filter, cost gate,
  provenance, and deterministic identity tests.

## Verification

- OOS contamination regression: RED before implementation, then GREEN.
- Volume candidate tests: RED before implementation, then GREEN at **5 passed**.
- Mutation: lowering the fixed volume threshold from 1.5 to 1.0 caused the no-volume-
  confirmation test to RED; reverted successfully.
- Relevant evaluator tests: **17 passed**.
- Full suite: **692 passed, 4 skipped, 0 failed**.

## Pre-registered public-history result

Fixed config: `MIN_RETURN=0.005`, `MIN_VOLUME_ZSCORE=1.5`, ATR target 1.5x,
ATR stop 1.0x, 5-minute expiry, real funding enabled, chronological 90-window
walk-forward, OOS-only trade PnLs, 30-trade minimum.

| Dataset | OOS trades | OOS profitable windows | Net PnL | OOS expectancy CI | Gate |
|---|---:|---:|---:|---|---|
| ADAUSDT 1m | 2 | 0/90 | -0.00101 | [-0.0000291, 0.0] | blocked: inadequate/negative |
| BTCUSDT 1m | 0 | 0/90 | 0.00 | [0.0, 0.0] | blocked: inadequate |
| ETHUSDT 1m | 0 | 0/90 | 0.00 | [0.0, 0.0] | blocked: inadequate |

The candidate is not profitable evidence. It is rejected/inconclusive because the
sample is inadequate and no dataset clears the positive expectancy gate. No tuning
was performed after inspecting these results.

## Honest conclusion

The most valuable result here is evaluator correctness plus a clean falsification of
one plausible feature hypothesis on the current corpus. The strategy cannot be
promoted, and the new v2 features are not evidence of edge by themselves.

Current gate: **promotion blocked; baseline negative; funded execution disabled**.

## Next alpha gate

Acquire or normalize historical public order-flow/depth proxies and funding/basis
series, reserve an untouched holdout before inspecting outcomes, then test one
structurally distinct funding/basis or flow-divergence hypothesis. Do not expand the
current impulse threshold search on the same corpus.
