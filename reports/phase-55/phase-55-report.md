# Phase 55 — Alpha pivot: causal features and controlled two-sided experiment

**Status:** completed research slice; experimental family rejected for promotion.
**Safety:** offline public-history replay only; no signed calls, no orders, no live execution.

## Why this phase

The project had spent many phases strengthening governance while its strategy layer
remained a few long-only textbook stubs. This phase redirected effort toward alpha:
write a falsifiable thesis, add causal market-context features, and test a structural
correction without changing the historical baseline.

## Changes

- `docs/ALPHA_RESEARCH_THESIS.md`: explicit hypothesis, mechanism, data, falsification,
  limitations, and promotion protocol.
- `src/features/technical.py`: retained v1 compatibility and added provenance-preserving
  v2 `return_1`, `return_3`, `atr`, `volume_zscore`, `funding_rate`, `open_interest`,
  and explicit neutral `open_interest_change` when no history is available.
- `src/strategies/two_sided.py`: isolated experimental family for symmetric trend,
  mean-reversion, and breakout signals. The default baseline registry was not changed.
- `tests/test_research_features.py`: causal/provenance/optional-data tests.
- `tests/test_two_sided_strategies.py`: side symmetry and stop/target geometry tests.

## RED / GREEN / mutation evidence

- Feature tests were observed RED before implementation: missing v2 feature keys and
  version mismatch (5 failures).
- Two-sided tests were observed RED before implementation: old generators returned no
  bearish candidates (3 failures).
- After implementation: targeted alpha tests and legacy strategy/cost tests passed
  (`36 passed`).
- Mutation: forced two-sided trend to always emit `BUY`; the bearish-side test went RED;
  the mutation was reverted and the test returned GREEN.

## Real public-history replay

Command used: bounded Python replay over every committed local `data/history/*.json`,
chronological walk-forward with `BaselineConfig(real_funding=True)`, evaluating the
experimental strategy family independently per symbol. `corpus_manifest.json` was
excluded.

| Dataset | Strategy | Closed trades | Profitable windows | Windows | Net PnL |
|---|---|---:|---:|---:|---:|
| ADAUSDT 1m | two-sided breakout | 99 | 16 | 90 | -0.03 |
| ADAUSDT 1m | two-sided mean reversion | 2 | 1 | 90 | ~0.00 |
| ADAUSDT 1m | two-sided trend | 4 | 1 | 90 | ~0.00 |
| BTCUSDT 1m | two-sided breakout | 91 | 4 | 90 | -9919.09 |
| BTCUSDT 1m | two-sided mean reversion | 0 | 0 | 90 | 0.00 |
| BTCUSDT 1m | two-sided trend | 0 | 0 | 90 | 0.00 |
| ETHUSDT 1m | two-sided breakout | 91 | 4 | 90 | -311.76 |
| ETHUSDT 1m | two-sided mean reversion | 0 | 0 | 90 | 0.00 |
| ETHUSDT 1m | two-sided trend | 0 | 0 | 90 | 0.00 |

The experiment is **not profitable** and is **not promoted**. The breakout family is
particularly poor on BTC and ETH. The zero-trade families are not evidence of safety
or edge; they are insufficiently active under this replay and remain unproven.

A bounded 500-candle BTC slice was also measured: default baseline net `-308.62`
(3 trades) versus experimental net `-165.53` (2 trades). The larger multi-symbol
replay overrides that optimistic, tiny-sample slice.

## Honest conclusion

This phase produced engineering progress and a falsifiable negative result, not
profitability. The likely dominant failure is not simply long-only bias: the breakout
signal remains structurally mis-specified and cost/exit behavior dominates. No
parameter tuning or live deployment is justified.

Current gate: **promotion blocked; baseline negative; funded execution disabled**.

## Next highest-leverage research gate

Add historical order-flow/depth proxies and a proper label/holding-period analysis,
then test one structurally distinct hypothesis (funding/basis or flow/price
 divergence) with purged chronological validation. Do not add more indicators to the
current breakout until its failure is attributed by gross edge versus cost, adverse
selection, and exit distribution.
