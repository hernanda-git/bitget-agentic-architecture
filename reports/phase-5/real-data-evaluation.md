# Phase 5 addendum: real public historical data evaluation

**Work unit:** acquire real unauthenticated Bitget public market history and evaluate
the deterministic cost-inclusive baseline on it, instead of only the synthetic fixture.

**Boundary honored:** all fetches used the demo product type `SUSDT-FUTURES` via the
unauthenticated public API (`api.bitget.com`). Zero signed calls, zero credentials,
zero orders, zero transfers.

## What changed

1. **Public client boundary fix (bug).** `BitgetPublicClient` previously allowed the
   live product type `USDT-FUTURES` and rejected the project-mandated demo type
   `SUSDT-FUTURES` (contradicting `docs/DEMO_ONLY.md`). Now only `SUSDT-FUTURES` is
   accepted and the default product type is `SUSDT-FUTURES`. `scripts/run_public_shadow.py`
   and `tests/test_phase4_market.py` were updated to match.
2. **Paged candle history.** `fetch_candles` gained `end_time_ms` / `allow_partial`
   parameters; `fetch_candle_history` paginates backward, dedupes overlaps, and stops
   on an empty page or `max_candles`.
3. **Public funding history.** `fetch_history_funding_rate` reads
   `/api/v2/mix/market/history-fund-rate` (unauthenticated) and normalizes to
   chronological `(funding_time_ms, rate)` records.
4. **Durable dataset.** `src/market/history.py` adds `HistoryDataset` (candles +
   funding + assumed half-spread, SHA-256 integrity-checked JSON round-trip that
   detects tampering) and `snapshots_from_dataset` which builds evaluation
   `MarketSnapshot`s with a trailing candle window.
5. **Realistic funding (bug fix).** The replay previously charged `funding_bps` on
   *every* minute-bar market event, so dense 1m history overstated funding by the
   number of bars between settlements (~480x for 1m vs 8h). Funding is now charged
   only on bars at/after an actual funding settlement, using the real settlement rate.
   The synthetic proxy path is preserved via `BaselineConfig.real_funding=False`
   (default) so existing fixtures and the cost-stress doubling test are unchanged.
6. **Runner.** `scripts/evaluate_real_history.py` fetches (or loads) a dataset and runs
   the same `run_baseline` / `run_walk_forward` / `run_cost_stress` engine, writing
   `reports/phase-5/real-data-baseline.json`.

## Live acquisition (unauthenticated)

- Command: `python3 scripts/evaluate_real_history.py --symbol BTCUSDT --granularity 1m --max-candles 1500 --fetch --output reports/phase-5/real-data-baseline.json`
- Acquired: `1500` 1m candles + `20` funding records for `BTCUSDT` / `SUSDT-FUTURES`.
- Network calls: `2` candle pages + `1` funding page (all public, unauthenticated).
- Signed calls: `0`. Orders: `0`. Credentials used: `none`.

## Raw evaluation metrics (real data)

| Metric | Value |
|---|---|
| Snapshots (1m bars) | `1500` |
| Closed trades | `1335` |
| Orders placed | `1395` (incl. `60` end-of-replay closes) |
| Open positions at end | `0` |
| Protection attachments | `1335` |
| Reconciliation checks | `0` (offline simulator, not an exchange adapter) |
| Gross PnL | `-132473.40` (mark-to-mark before costs) |
| Fees | `105659.87` (5 bps entry+exit) |
| Spread | `10565.99` (assumed 0.5 bps half-spread) |
| Slippage | `42263.94` (assumed 2 bps) |
| Funding | `229.02` (real settlement rates, corrected) |
| **Net PnL** | **`-291192.22`** |
| Promotion allowed | `false` |
| Promotion reason | `NEGATIVE_NET_PNL` |

### Funding-model correction impact
Before the fix, funding on this dataset read `665478.30` (a per-bar artifact). After the
fix it reads `229.02` — the dominant PnL term was fictitious. The corrected, dominant
cost is now fees (`105659.87`), which is real under the 5 bps assumption. Net PnL remains
negative and is now a defensible figure rather than a funding artifact.

### Strategy attribution (closed trades)
- `volatility_breakout`: `1328` trades, net `-290098.90`
- `mean_reversion`: `5` trades, net `-1135.94`
- `trend_continuation`: `2` trades, net `+42.62`

On real 1m BTCUSDT, the `volatility_breakout` candidate fires on nearly every bar and is
the entire loss driver. This is a genuine strategy-quality signal, not a cost artifact.

### Walk-forward (54 complete 10-snapshot windows)
- Total closed trades across windows: `505`
- Per-window net PnL: min `-2922.06`, max `+574.70`, mean `-1080.64`
- Every window was evaluated on unseen test data after an expanding train + embargo.

### Cost stress (multipliers 1.0 / 1.5 / 2.0 on fees, funding, slippage)
- Net PnL: `-291192.22` / `-363672.07` / `-437245.25`
- Fees: `105659.87` / `157656.79` / `210209.07`
- Funding is held at real settlement rates under stress (not scaled), which is the
  honest treatment for observed funding history.

## Runtime / resource
- Resource guard before work: `ok` (disk 42.9% used, swap 69.3%, 1.7 GB free RAM).
- Full suite: `234 passed`. `compileall -q src scripts tests`: clean.

## Limitations and safety
- Historical bid/ask is not available from the public API; spread is a documented
  assumed half-spread (`0.5` bps) and is reported as an assumption, not observed data.
- Funding uses real public settlement rates from `history-fund-rate`; fees and slippage
  remain configured stress assumptions (5 bps / 2 bps).
- This is an offline paper replay on retrieved history. It performs no venue
  reconciliation, no out-of-sample validation on independent symbols, and no parameter
  fitting. It does not and cannot place orders.
- Phase 6 bounded LLM selection remains blocked (`NEGATIVE_NET_PNL`). Promotion stays
  disabled. No funded execution occurred.
- Dataset file `data/history/BTCUSDT_1m.json` is git-ignored (reproducible via `--fetch`);
  only the report JSON and this document are committed.
