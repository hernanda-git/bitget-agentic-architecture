# Phase 57 — Causal order-flow proxies, holding-period labels, and impulse candidate

**Status:** completed; research infrastructure only; no profitability claim.
**Safety:** offline/public-history compatible; no signed calls, no orders, no live execution.

## Why this phase

The Phase 56 audit identified the next alpha gate: order-flow/depth proxies and
proper holding-period labels. An autonomous tick started this work but was
interrupted with a stranded mutation (`market_impact` guard flipped to `==`) and
garbage prepended to `src/strategies/orderflow_impulse.py`. This tick finished,
verified, and committed the complete work instead of starting a competing phase.

## Changes

- `src/features/technical.py`
  - `close_location_value`: causal close position within the latest candle range
  - `volume_pressure`: CLV deviation combined with volume anomaly
  - `market_impact_proxy`: latest candle body/range ratio
  - `spread_proxy`: observed bid/ask spread in basis points
  - `make_holding_period_labels`: forward-return labels over a fixed positive
    holding period, with entry/exit timestamps and symbol provenance
- `src/strategies/orderflow_impulse.py` (NEW)
  - `generate_orderflow_impulse`: isolated order-flow impulse candidate using
    CLV deviation, volume pressure confirmation, market impact direction guard,
    and spread filter. Fixed parameters: HOLDING_PERIOD_BARS=5,
    MIN_CLV_DEVIATION=0.15, MIN_VOLUME_PRESSURE=0.05, MAX_SPREAD_BPS=5.0.
  - Market impact direction guard verified binding via mutation: flipping `!=` to
    `==` causes `test_market_impact_must_confirm_direction` to go RED.
- `tests/test_orderflow_depth_features.py`: 12 tests covering geometry, signs,
  neutral flat bars, provenance, causal behavior, label horizons, errors, and
  negative returns.
- `tests/test_orderflow_impulse.py`: 8 tests covering bullish/bearish emission,
  CLV deviation rejection, market impact direction guard, high spread rejection,
  cost gate, provenance determinism, and expiry matching.
- `tests/test_orderflow_evaluation.py`: 5 tests covering holding-period labels,
  baseline run, walk-forward, combined cost stress (fail-closed), and net PnL
  non-positive assertion.

## Verification

- RED confirmed: stranded mutation (`market_impact > 0 == clv_signal > 0`) caused
  `test_market_impact_must_confirm_direction` to pass incorrectly; reverted to
  `!=` guard, test went RED, reverted to correct `!=`, test GREEN.
- GREEN: **25 targeted order-flow tests passed** (12 depth + 8 impulse + 5 eval).
- Full baseline: **717 passed, 4 skipped, 0 failed**.
- Mutation verification: inverted `market_impact` guard confirmed binding (test went RED).
- Garbage prepended to `orderflow_impulse.py` cleaned (system error messages
  removed from file head).
- compileall clean; secret scan clean; no /opt/bots/bitget-listener dependencies.
- No future candles used by any proxy feature.

## Honest status

This phase adds measurement capability only. It does not change the canonical
baseline or promote any strategy. The current baseline remains negative and
funded execution remains disabled. The order-flow impulse candidate produces
negative net PnL under purged chronological walk-forward evaluation with
realistic cost stress.

## Next alpha gate

Use these proxies and holding-period labels in one structurally distinct
funding/basis or flow hypothesis, with purged chronological evaluation and
realistic fee/funding/spread/slippage/latency stress. Do not tune thresholds
against current public-history results. Acquire actual historical depth/order-flow
data before making claims about microstructure edge. Do not promote the current
breakout family. No profitability claim is allowed.
