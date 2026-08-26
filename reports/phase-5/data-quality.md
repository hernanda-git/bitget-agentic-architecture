# Phase 5 addendum: dataset data-quality gate and expanded real history

**Work unit:** add fail-closed structural data-quality validation for historical
datasets, wire it into the real-history evaluator, and acquire a larger real public
dataset (BTCUSDT 5m, ~7 days) for stronger walk-forward evidence.

**Boundary honored:** all network traffic was unauthenticated public Bitget market
data (`SUSDT-FUTURES` demo product type via `api.bitget.com`). Zero signed calls,
zero credentials, zero orders, zero transfers. `/opt/bots/bitget-listener` untouched.

## What changed

1. `src/market/history.py` adds `expected_interval_ms(granularity)` and
   `DataQualityReport` / `data_quality_report(dataset)`, measuring: duplicate
   timestamps, non-chronological ordering, missing-bar gaps (with per-gap
   `missing_bars`), zero-volume bars, and funding coverage against the 8h settlement
   cadence. `ok` is structural soundness only; gaps and funding coverage are reported
   as measured facts, never silently dropped.
2. `scripts/evaluate_real_history.py` now runs the quality gate **before** any
   evaluation and fails closed (exit code 2, no output artifact) on structurally bad
   datasets, and embeds the full `data_quality` block into the payload.
3. New durable dataset `data/history/BTCUSDT_5m.json`; refreshed
   `reports/phase-5/real-data-baseline.json` (adds `data_quality`, core metrics
   byte-identical to the previous run, confirming replay determinism).

## TDD evidence

- RED: 6 new tests failed with `ImportError` (`data_quality_report` /
  `expected_interval_ms` missing), then 2 CLI-wiring tests failed for the expected
  reasons (no gate, no payload field).
- GREEN: minimal implementation; focused file 20/20, full suite green.
- Mutation checks (build-verification discipline):
  - disabling duplicate detection (`if ts in seen:` -> `if False:`) failed exactly
    `test_data_quality_report_flags_duplicate_and_regressing_timestamps` and
    `test_evaluator_cli_fails_closed_on_structurally_bad_dataset`;
  - zeroing `missing_bars` in gap entries failed exactly
    `test_data_quality_report_reports_missing_bar_gaps`;
  - restore confirmed byte-identical source and a fully green suite.

## Live acquisition (unauthenticated public API only)

- Command: `python3 scripts/evaluate_real_history.py --symbol BTCUSDT --granularity 5m --max-candles 2000 --funding-limit 200 --fetch --output reports/phase-5/real-data-5m-baseline.json`
- Acquired: `2000` 5m candles + `20` funding records for `BTCUSDT` / `SUSDT-FUTURES`.
- Network calls: `3` total (`2` candle pages + `1` funding page), all public and
  unauthenticated. Signed calls: `0`. Orders: `0`. Credentials used: `none`.
- Coverage window: 2026-08-19 17:10 WIB through 2026-08-26 15:45 WIB (~6.9 days).

## Data-quality measurements

| Check | BTCUSDT 1m (1500 bars) | BTCUSDT 5m (2000 bars) |
|---|---|---|
| Structural ok | `true` | `true` |
| Duplicate timestamps | `0` | `0` |
| Non-chronological | `0` | `0` |
| Missing-bar gaps | `0` (max missing bars `0`) | `0` (max missing bars `0`) |
| Zero-volume bars | `0` | `0` |
| Funding settlements expected / found / missing | `3 / 3 / 0` | `20 / 20 / 0` |

## Raw evaluation metrics (real 5m data, cost-inclusive)

| Metric | Value |
|---|---|
| Snapshots (5m bars) | `2000` |
| Closed trades | `250` (orders `251`, incl. end-of-replay close) |
| Open positions at end | `0` |
| Protection attachments | `250` |
| Gross PnL | `+15079.90` |
| Fees (5 bps entry+exit) | `18902.83` |
| Spread (assumed 0.5 bps half-spread) | `1890.28` |
| Slippage (assumed 2 bps) | `7561.13` |
| Funding (real settlement rates) | `59.54` |
| **Net PnL** | **`-13333.89`** |
| Promotion allowed | `false` (`NEGATIVE_NET_PNL`) |

Walk-forward on the same 5m data: `72` complete non-overlapping test windows,
`120` closed trades, summed window net PnL `-13423.75`. Per-strategy attribution
across walk-forward windows: `volatility_breakout` `-8085.93` (70 trades),
`trend_continuation` `-3843.87` (33), `mean_reversion` `-1493.95` (17). Every
strategy is negative; there is no hidden profitable component to cherry-pick.

Baseline regime attribution (full-sample 5m): losses concentrate in `RANGING`
(197 trades, net `-12935.37`); `TRENDING` (2 trades, `+1370.08`) and
`DATA_DEGRADED` (1 trade, `+160.75`) are positive but far too few trades to be
evidence. Cost-stress multipliers degrade monotonically as expected.

The existing 1m dataset re-evaluated identically after the change
(net `-5224.3824`, 54 windows), proving the gate did not alter evaluation semantics.

## Verification commands

```text
python3 scripts/resource_guard.py --json          # ok:true, violations: []
python3 -m pytest tests/test_public_history.py -q # 20 passed
python3 -m pytest -q                              # 243 passed
python3 -m compileall -q src scripts tests        # clean
python3 scripts/evaluate_real_history.py ...      # commands above
python3 scripts/verify_phase5_report.py --root .  # ok:true, errors:[]
```

## Limitations and negative findings

- The deterministic baseline remains **negative** on every real dataset evaluated;
  the Phase 6 bounded LLM selection gate and all promotion actions stay blocked.
- Positive gross PnL on 5m data (+15079.90) is fully consumed by realistic costs
  (fees + spread + slippage + funding = 28413.79); gross-positive-before-costs must
  not be reported as profitability.
- Spread is still an assumed constant half-spread, not observed order-book history;
  slippage is a configured fill impact. Both are documented assumptions, not venue reads.
- Funding coverage is measured against an assumed uniform 8h cadence; if the venue
  changes settlement intervals the expectation must be updated.
- `ok` covers structural soundness only; a dataset with large-but-clean gaps passes
  the gate and its gaps are surfaced in the report instead of blocking evaluation.
- Offline simulator has no reconciliation checks by construction; venue read-back
  evidence remains out of scope for this research path.
