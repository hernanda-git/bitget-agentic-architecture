# Phase 5 summary: deterministic strategy and research engine

## Gate verdict

`BLOCKED`: the deterministic baseline is negative after fees, funding, and simulated slippage. Promotion is disabled, and Phase 6 must not begin.

## Raw run metrics

- Mode: `offline-paper-replay`
- Snapshots replayed: `36`
- Network calls: `0`
- Signed calls: `0`
- Orders: `36`
- Open positions at replay end: `1`
- Closed trades: `35`
- Fees: `3.334760285`
- Funding: `1.2428`
- Net PnL on closed trades: `-42.09813028500013`
- Promotion allowed: `false`
- Promotion reason: `NEGATIVE_NET_PNL`
- Replay hash: `7fd9201588e765b283d38db03b5f46728ebef818891136fc87ddf11bf11b5e3c`
- Walk-forward split: train `[0,20]`, embargo `[21]`, test `[22,35]`

The machine-readable raw result is in `reports/phase-5/baseline.json`. The durable gate artifact is `reports/phase-5/summary.json`.

## Implemented

- Versioned feature values with name, version, source snapshot hash, source timestamp, parameters, and value.
- Deterministic technical features: SMA, momentum, volatility, range high, and range low.
- Candidate generators for trend continuation, mean reversion, and volatility breakout.
- Candidate cost gate requiring expected move to exceed fees, funding, spread, and slippage.
- Complete candidate identity and execution fields, including expiry and feature snapshot hash.
- Deterministic regimes: `TRENDING`, `RANGING`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `LIQUIDATION_EVENT`, and `DATA_DEGRADED`.
- Baseline runner using the existing offline `FakeExchange` paper simulator, closed-trade fee/funding accounting, and deterministic replay hashes.
- Strategy and regime breakdowns, fee/funding fields, and walk-forward-compatible split metadata.

## Limitations and safety

The adverse replay fixture is synthetic and is not evidence of live profitability or loss rates. One position remained open at replay end and is excluded from closed-trade PnL. No network, signed, demo, or live exchange calls were made. The negative result is reported as-is, with no profitability claim. Phase 6 is explicitly blocked.
