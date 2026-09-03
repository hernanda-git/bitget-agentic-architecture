# Phase 57 — Causal order-flow proxies and holding-period labels

**Status:** completed; research infrastructure only; no profitability claim.
**Safety:** offline/public-history compatible; no signed calls, no orders, no live execution.

## Why this phase

The Phase 56 audit identified the next alpha gate: order-flow/depth proxies and
proper holding-period labels. An autonomous tick started this work but was
interrupted with a stranded mutation and an undefined `volume_pressure` value.
This phase finished and verified that work instead of starting a competing phase.

## Changes

- `src/features/technical.py`
  - `close_location_value`: causal close position within the latest candle range
  - `volume_pressure`: CLV deviation combined with volume anomaly
  - `market_impact_proxy`: latest candle body/range ratio
  - `spread_proxy`: observed bid/ask spread in basis points
  - `make_holding_period_labels`: forward-return labels over a fixed positive
    holding period, with entry/exit timestamps and symbol provenance
- `tests/test_orderflow_depth_features.py`: 12 tests covering geometry, signs,
  neutral flat bars, provenance, causal behavior, label horizons, errors, and
  negative returns.

These are **candle-derived proxies**, not true historical depth or order-flow
records. They must not be presented as exchange order-book truth.

## Verification

- Interrupted RED state confirmed: 7 order-flow tests failed, including a stranded
  CLV mutation and missing `volume_pressure` implementation.
- GREEN: **12 targeted tests passed** after restoring the implementation.
- Mutation verification: inverted `volume_pressure` sign; directional sign test went
  RED; reverted successfully.
- No future candles are used by the proxy features.

## Honest status

This phase adds measurement capability only. It does not change the canonical
baseline or promote any strategy. The current baseline remains negative and
funded execution remains disabled.

## Next alpha gate

Use these proxies and holding-period labels in one isolated, pre-registered flow /
impulse candidate, with purged chronological evaluation and realistic cost stress.
Do not tune thresholds against the current public-history results. Acquire actual
historical depth/order-flow data before making claims about microstructure edge.
