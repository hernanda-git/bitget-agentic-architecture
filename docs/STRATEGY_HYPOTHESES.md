# Strategy hypotheses

This registry is independent of strategy selection, parameter tuning, and
promotion decisions. Each hypothesis must be falsifiable and evaluated on
held-out data.

| ID | Mechanism | Data | Features | Entry / exit | Cost edge | Falsification | Failure modes | Data exclusions | OOS gate |
|---|---|---|---|---|---|---|---|---|---|
| H-001 | Trend persistence after directional impulse | Offline candle history with verified chronology | Momentum, volatility, regime | Enter after confirmed directional move; exit at stop or target | Expected move must exceed fees, spread, slippage, and funding | Negative net PnL or failure across embargoed walk-forward windows | Choppy markets, stale data, spread widening, partial fills | Duplicate, malformed, stale, or incomplete records | Minimum sample, cost-inclusive positive OOS evidence, no unmodeled funding |

## Required fields

Every registry entry must specify:

- mechanism
- data source and coverage
- features
- entry and exit rules
- cost edge
- falsification criterion
- failure modes
- data exclusions
- out-of-sample gate

A hypothesis is not evidence of profitability. Negative results remain part of
the record and cannot be deleted or tuned away.
