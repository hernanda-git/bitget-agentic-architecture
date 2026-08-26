# Phase 5 addendum: non-overlapping per-strategy entry model in the baseline replay

**Work unit:** remove unrealistic position stacking from `run_baseline` (2026-08-26 14:34 WIB).

**Boundary honored:** offline work only. The re-evaluation loaded the previously stored
dataset (`data/history/BTCUSDT_1m.json`); zero network calls, zero signed calls, zero
credentials, zero orders, zero transfers.

## Problem

The previous real-data evaluation showed `volatility_breakout` opening a trade on
nearly every bar (1335 closed trades on 1500 one-minute bars). The replay engine gave
each strategy a fresh `FakeExchange` per snapshot and never checked whether that
strategy already held an open simulated position, so a signal persisting across
consecutive bars stacked dozens of overlapping entries. A real bot holds one position
per strategy; the churn model overstated both trade count and cost drag.

## Change (strict TDD)

1. **RED:** new test `test_baseline_never_stacks_overlapping_entries_for_one_strategy`
   builds 12 snapshots with a persistent breakout condition whose stop/target band is
   never touched, then asserts exactly 1 closed trade. Verified RED for the expected
   reason: `assert 12 == 1` failed.
2. **GREEN:** `run_baseline` now tracks `busy_until[name]`: after an entry, the
   strategy is blocked from re-entering until the bar its previous position actually
   closed (the exit bar itself included). Positions still open at the evaluation end
   block re-entry through `evaluation_end`.
3. Two existing tests encoded the old stacking counts and were updated to measured
   values: `orders == 16` (was 37), end-of-replay spread `0.30` (was 0.72) on the
   synthetic fixture. Determinism double-run confirmed identical results.

## Verification

- Focused: `tests/test_phase5_engine.py::test_baseline_never_stacks_overlapping_entries_for_one_strategy` RED then GREEN.
- Full suite: `235 passed` (`.venv/bin/python -m pytest tests/ -q`).
- `compileall -q src scripts tests`: clean.
- Mutation checks on the new guard:
  - gate disabled (`if False:`): the new test fails (1 failed);
  - off-by-one loosened (`close_index - 1`): 4 tests fail;
  - restored from backup: file byte-identical, full suite green again.

## Raw re-evaluation metrics

### Synthetic fixture (`scripts/run_strategy_baseline.py`)

| Metric | Before | After |
|---|---|---|
| Orders | 37 | 16 |
| Closed trades | 36 | 15 |
| End-of-replay closes | 1 | 1 |
| Protection attachments | 36 | 15 |
| Net PnL | negative | `-22.63` (still negative) |

### Real public history, cached dataset (1500 x 1m BTCUSDT candles + 20 funding records, SUSDT-FUTURES)

| Metric | Before (stacking) | After (non-overlap) |
|---|---|---|
| Closed trades | 1335 | 35 |
| Orders | 1395 | 36 |
| End-of-replay closes | 60 | 1 |
| Protection attachments | 1335 | 35 |
| Fees | 105659.87 | 2769.78 |
| Spread | 10565.99 | 276.98 |
| Slippage | 42263.94 | 1107.91 |
| Funding | 229.02 | 4.51 |
| Gross PnL | -132473.40 | -1065.20 |
| **Net PnL** | **-291192.22** | **-5224.38** |
| Promotion allowed | false | false |
| Reason | NEGATIVE_NET_PNL | NEGATIVE_NET_PNL |

Strategy attribution after the fix:
- `volatility_breakout`: 30 trades, net `-4567.05` (still the loss driver)
- `mean_reversion`: 3 trades, net `-699.95`
- `trend_continuation`: 2 trades, net `+42.62`

Walk-forward (54 complete windows, unseen test slices): net min `-481.66`, max `+89.45`, mean `-108.68`.
Cost stress (1.0 / 1.5 / 2.0): net `-5224.38` / `-6228.22` / `-7889.38`.

## Honest interpretation

- Removing stacking cut gross loss ~124x and fees ~38x, but **the baseline is still
  negative**. The earlier catastrophic number was largely a churn artifact; the honest
  residual is that the candidates have no cost-inclusive edge on this window.
- No parameter was tuned to improve results; the only change is a structural realism
  constraint (one open position per strategy), applied identically to all strategies.
- Phase 6 bounded LLM selection remains blocked (`NEGATIVE_NET_PNL`). Promotion actions
  remain blocked.

## Limitations

- Offline paper replay on retrieved history; no venue reconciliation, no live fills.
- Spread remains a documented assumed half-spread (0.5 bps); historical bid/ask is not
  available from the public API.
- Single symbol, single ~25-hour window; walk-forward windows are correspondingly short.
- Resource guard before work: ok (disk 43.0% used, swap 71.6%, 1.7 GB free RAM).
