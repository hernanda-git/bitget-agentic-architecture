# Phase 5 research: expanded public history and walk-forward robustness

Date: 2026-08-26 17:19 WIB (Asia/Jakarta, UTC+7)

## Gate verdict

`BLOCKED` (unchanged). The deterministic baseline remains negative after fees,
real funding, spread, and simulated execution slippage on every dataset
evaluated. Promotion to Phase 6 bounded LLM selection stays disabled. Work in
this unit was unblocked research and engineering only: no orders, no signed
calls, no credentials, no connection to any deployed bot tree.

## What this work unit changed

1. `summarize_walk_forward` added to `src/evaluation/baseline.py` (TDD: RED on
   ImportError and empty-rows ValueError first, then minimal implementation).
   It aggregates walk-forward windows into robustness facts: window count,
   windows with trades, profitable windows, closed trades, total/worst/best
   window net PnL.
2. The real-history evaluator (`scripts/evaluate_real_history.py`) now embeds a
   `walk_forward_summary` block computed from the same rows it reports (TDD:
   RED KeyError on missing payload key, then one-line wiring).
3. Funding history acquisition fixed and hardened:
   - The Bitget v2 endpoint was being queried with `limit`, which the venue
     ignores; it silently applied its default page size of 20 records. The
     client now sends `pageSize` (TDD: RED KeyError on request params, then fix).
   - `fetch_funding_history` now paginates backward from `end_time_ms`,
     dedupes overlaps, and stops on an empty or duplicate page (TDD: RED on
     both stub-driven tests first). This raised funding coverage for the
     6000-candle 5m datasets from 20 records (`funding_missing=42`) to 100
     records (`funding_missing=0`).
4. `scripts/baseline_check.py` now parses both pytest summary styles so the
   checked-in baseline artifact reports a truthful test count (TDD: RED on
   missing parser function, then implementation).

## Raw verified run metrics

Network calls in this work unit were unauthenticated public market-data reads
only (Bitget v2 mix/market candles and history-fund-rate). Signed calls: `0`.
Orders: `0`. Positions: `0`. Fees/funding/PnL below are replay accounting over
public candles, not exchange-proven outcomes.

Command pattern:

```text
.venv/bin/python scripts/evaluate_real_history.py --symbol <SYM> --granularity 5m \
    --max-candles 6000 --funding-limit 500 --fetch \
    --output reports/phase-5/<artifact>.json
```

### BTCUSDT 5m, 6000 candles (~20.8 days), artifact `reports/phase-5/real-data-5m-expanded.json`

- Candle range: 2026-08-05 21:15 WIB to 2026-08-26 17:10 WIB
- Data quality: ok=true, gaps=0, max_missing_bars=0, zero_volume_bars=0,
  duplicate_timestamps=0, non_chronological=0, funding_missing=0
  (100 funding records)
- Baseline replay: snapshots=6000, orders=353, closed_trades=353, open=0,
  protection_attachments=353, network_calls=0, signed_calls=0
- Gross PnL: +13222.50 ; Fees: -25539.04 ; Spread: -2553.90 ;
  Slippage: -10215.62 ; Real funding: -137.92
- Net PnL: -25223.98 -> promotion_allowed=false, NEGATIVE_NET_PNL
- Strategy attribution (net): trend_continuation -9863.67 (123 trades),
  volatility_breakout -11868.92 (181), mean_reversion -3491.39 (49)
- Walk-forward summary (218 windows of 10 snapshots):
  windows_with_trades=204, profitable_windows=48, closed_trades=378,
  total_net=-32489.93, worst_window=-2422.22, best_window=+2074.31
- Cost stress net PnL: x1.0 = -25223.98, x1.5 = -30385.90, x2.0 = -33666.20

### ETHUSDT 5m, 6000 candles (~20.8 days), artifact `reports/phase-5/real-data-5m-ethusdt.json`

- Candle range: 2026-08-05 21:20 WIB to 2026-08-26 17:15 WIB
- Data quality: ok=true, gaps=0, max_missing_bars=0, zero_volume_bars=0,
  duplicate_timestamps=0, non_chronological=0, funding_missing=0
  (100 funding records)
- Baseline replay: snapshots=6000, orders=467, closed_trades=467, open=0,
  protection_attachments=467, network_calls=0, signed_calls=0
- Gross PnL: +719.35 ; Fees: -1038.16 ; Spread: -103.82 ;
  Slippage: -415.26 ; Real funding: -6.00
- Net PnL: -843.89 -> promotion_allowed=false, NEGATIVE_NET_PNL
- Strategy attribution (net): trend_continuation -480.75 (186 trades),
  volatility_breakout -267.82 (179), mean_reversion -95.32 (102)
- Walk-forward summary (218 windows of 10 snapshots):
  windows_with_trades=198, profitable_windows=47, closed_trades=423,
  total_net=-1177.55, worst_window=-62.38, best_window=+108.82
- Cost stress net PnL: x1.0 = -843.89, x1.5 = -939.39, x2.0 = -950.08

## Honest interpretation

- Gross edge is positive on both symbols but smaller than fees alone; the
  deterministic candidates trade too often at 1 quantity per entry and pay the
  full round-trip cost each time. No result here was tuned to look better.
- Walk-forward confirms breadth-level robustness failure: only about 22% of
  windows are profitable on either symbol, and total walk-forward net is worse
  than the single-split baseline on BTCUSDT.
- Strategy attribution shows all three candidate generators lose money after
  costs; there is no single strategy to rescue by re-weighting.
- ETHUSDT loses far less than BTCUSDT under identical rules, driven by lower
  per-trade cost relative to price; this is a cost-scale observation, not edge.

## Verification evidence

- Focused RED runs observed before each implementation step (ImportError,
  KeyError, and stub-behavior assertion failures quoted above).
- Full suite after all changes: `245 passed` after unit A/B, `248` after the
  funding fixes, `251 passed` final including the baseline-collector fix
  (`.venv/bin/python -m pytest tests/ -q`).
- `compileall src scripts tests`: clean.
- Mutation check on the new summary wiring: reverting the evaluator payload key
  reproduces the RED test exactly (KeyError `walk_forward_summary`), and
  restoring returns it green.
- Bonus fix surfaced by evidence regeneration: `scripts/baseline_check.py`
  mis-parsed modern pytest summaries (`248 tests collected`) and, with its
  12k output cap, undercounted tests as 140 in the stale checked-in baseline.
  Now parses both summary styles; regenerated
  `reports/baseline/latest.json` reports test_count=251 truthfully.

## Limitations

- Historical bid/ask is unavailable from the public API; spread remains an
  explicit assumption (assumed half-spread 0.5 bps) charged in replay, not an
  observation.
- The venue returns at most 100 historical funding settlements, which fully
  covers these ~21-day windows but would not cover longer histories.
- Replay fills are simulated from candle closes plus assumed half-spread and
  configured slippage; nothing here is exchange-proven execution evidence.
