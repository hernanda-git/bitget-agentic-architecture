# Strategy hypotheses

This registry is independent of strategy selection, parameter tuning, and
promotion decisions. Each hypothesis must be falsifiable and evaluated on
held-out data.

Every hypothesis is bound to the directive sec. 3 factor ontology via a
`category` field (canonical mirror: `src/evaluation/factor_ontology.py`).
Coverage of the factor space is measurable: `coverage_summary(registry)` reports
how many of the seven ontology categories are represented by at least one
hypothesis and flips `promotion_ready` to `True` only when all seven are
represented. A promotion claim is therefore fail-closed against blind spots in
the factor map.

| ID | Category | Mechanism | Data | Features | Entry / exit | Cost edge | Falsification | Failure modes | Data exclusions | OOS gate |
|---|---|---|---|---|---|---|---|---|---|---|
| H-001 | time_structure | Trend persistence after directional impulse | Offline candle history with verified chronology | Momentum, volatility, regime | Enter after confirmed directional move; exit at stop or target | Expected move must exceed fees, spread, slippage, and funding | Negative net PnL or failure across embargoed walk-forward windows | Choppy markets, stale data, spread widening, partial fills | Duplicate, malformed, stale, or incomplete records | Minimum sample, cost-inclusive positive OOS evidence, no unmodeled funding |
| H-002 | onchain | Holder-cost reversion when MVRV/NUPL signals extremes | Offline on-chain holder-cost and supply snapshots | MVRV, NUPL, holder cost bases, HODL waves | Enter on extreme unrealized-PnL reversion; exit at mean reversion or stop | Move must exceed fees, spread, slippage, and funding | Negative net PnL or failure across embargoed walk-forward windows | Lagged on-chain feeds, regime shift, exchange-flow noise | Stale or out-of-order on-chain snapshots | Minimum sample, cost-inclusive positive OOS evidence |
| H-003 | derivatives_microstructure | Funding-extreme mean reversion before settlement | Offline perp funding, OI, and liquidation-cascade history | Perp funding, OI/volume divergence, liquidation cascades, book depth | Enter against funding extreme; exit at funding normalization or stop | Move must exceed fees, spread, slippage, and funding | Negative net PnL or failure across embargoed walk-forward windows | Funding regime change, crowded trade, venue inventory shock | Missing or zero funding records, non-8h-aligned settlement | Minimum sample, cost-inclusive positive OOS evidence |
| H-004 | adversarial | Liquidation-hunt fade after cascade exhaustion | Offline liquidation-cascade and book-depth history | Liquidation cascades, spoofing/layering flags, bot crowding | Fade exhaustion of a cascade; exit at reload or stop | Move must exceed fees, spread, slippage, and funding | Negative net PnL or failure across embargoed walk-forward windows | Repeat cascade, spoof reversal, extraction by other bots | Incomplete cascade records, synthetic-book artifacts | Minimum sample, cost-inclusive positive OOS evidence |

## Required fields

Every registry entry must specify:

- mechanism
- data source and coverage
- features
- factor-ontology category
- entry and exit rules
- cost edge
- falsification criterion
- failure modes
- data exclusions
- out-of-sample gate

A hypothesis is not evidence of profitability. Negative results remain part of
the record and cannot be deleted or tuned away. Coverage of all seven
ontology categories is required before any promotion claim; absence of a
category is an explicit, visible gap in `coverage_summary`.

## Status (honest)

As of Phase 45 this registry (the doc) lists four candidate hypotheses spanning
`time_structure`, `onchain`, `derivatives_microstructure`, and `adversarial`.
The `macro_liquidity`, `flow_participation`, and `sentiment_attention`
categories remain unrepresented: `coverage_summary` reports them as
`unrepresented_categories` and `promotion_ready=False`. The deterministic
baseline remains negative; no profitability is claimed.
