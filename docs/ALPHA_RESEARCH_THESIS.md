# Alpha Research Thesis and Promotion Protocol

**Status:** research-only; no profitability claim; promotion remains blocked.

## Problem

The prior default strategy family was long-only and used short-window textbook
primitives. Its public-history aggregate was negative after fees, funding,
spread, and slippage. This document separates a controlled experimental family
from the historical baseline so any change in results remains attributable and
reproducible.

## Experiment A: directional symmetry

**Hypothesis:** A directional signal should express both BUY and SELL outcomes.
A long-only implementation is structurally biased in bearish regimes and cannot
measure whether the signal's direction, rather than market drift, carries useful
information.

**Mechanism:**
- continuation follows the sign of causal recent momentum;
- mean reversion fades the sign of causal SMA deviation;
- breakout trades either side of a prior-candle range;
- entry uses ask for BUY and bid for SELL;
- stop/target geometry is mirrored by side;
- candidates still require expected move to exceed all-in expected cost.

**Data:** committed/locally acquired public Bitget history only; no signed calls,
no orders, no credentials. Evaluation is chronological walk-forward with real
funding when available and fee/slippage assumptions explicit in the report.

**Falsification:** reject the family if it is negative on held-out aggregate,
negative across most symbols/windows, unstable under nearby cost assumptions, or
fails the minimum-trade/statistical gates. A positive backtest alone is not
promotion evidence.

**Known limitation:** this first experiment does not yet use order-book depth,
taker flow, or historical open-interest changes because the current snapshot
schema does not carry those time series. The new feature layer marks unavailable
optional values as neutral rather than inventing them.

## Experiment B: causal market-context features

Added provenance-preserving v2 features: 1/3-bar returns, ATR, volume z-score,
funding rate, open interest, and explicit open-interest-change availability.
These are research inputs, not a claim of edge. Any future strategy must declare
which features it uses and must pass the same walk-forward/cost gates.

## Promotion gate

No strategy is promoted from this experiment. Promotion requires, at minimum:
fee-inclusive positive net PnL, adequate closed-trade sample, positive held-out
expectancy with uncertainty support, stability across symbols/time/nearby costs,
realistic execution assumptions, and independent forward paper evidence. Until
then: shadow-only, promotion blocked, baseline status reported as negative.
