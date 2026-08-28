# Phase 36 — Observed order-book cost surface + fail-closed calibration (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-28 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline unit work + READ-ONLY live public Depth-of-Book calibration, zero orders
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not touch the deterministic gate. The observed spread calibrates cost models only; the deterministic baseline remains negative (see prior phases).

## Scope and why it is unblocked

The cron mandate lists `realistic cost/funding/slippage stress` and `data-quality checks` as unblocked streams. Prior cost-stress work modeled an *assumed* half-spread because the selected public candle endpoint exposes no historical bid/ask. This phase replaces that assumption with an **observed, real-venue** top-of-book spread and depth surface, fail-closed through the same quality-gate family used for candles.

Two pieces were already half-written (untracked) from a prior session: `src/market/orderbook.py` + `src/market/orderbook_quality.py` + `src/market/bitget_public.get_order_book` + `tests/test_order_book.py`. This run (a) retroactively proved those tests genuinely bind (RED isolation + mutation), (b) added a pure aggregation module `orderbook_calibration.py` + collector CLI `observe_orderbook.py` with their own TDD tests, and (c) ran a live, read-only observed-spread calibration over 8 symbols as raw evidence. Nothing here changes the promotion gate, places orders, or computes realized PnL.

## TDD cycle (strict)

### A. Order-book module + gate (pre-existing untracked work, retroactively proven)
- **RED (isolated this run):** moved `src/market/orderbook.py` + `src/market/orderbook_quality.py` aside; `pytest tests/test_order_book.py` failed at collection with `ModuleNotFoundError: No module named 'src.market.orderbook'` (feature absent, not a typo). Restored.
- **GREEN:** 8 passed (restored state).
- **Mutation check (build-verification skill):** applied 3 mutations — disable crossed-book guard in `parse_order_book` (`if bids[0][0] >= asks[0][0]:` -> `if False:`), force `top_spread_bps` to return `0.0`, and disable crossed detection in `check_order_book` (`if ... >= ...` -> `if False:`). The 3 targeted tests (`test_parse_order_book_rejects_crossed_book`, `test_top_spread_bps_computes_correctly`, `test_check_order_book_flags_crossed_book`) all FAILED red, then reverted to 8 passed. Proves the assertions bind to the guards.

### B. Calibration aggregation (`src/market/orderbook_calibration.py`)
- **RED:** `tests/test_orderbook_calibration.py` written first; `from src.market.orderbook_calibration import summarize_spreads` -> `ModuleNotFoundError`. 3 failed.
- **GREEN:** implemented `summarize_spreads(obs, *, now_ms, max_age_ms)` aggregating per-symbol spread (median/mean bps) and depth within 5/60 bps bands; fail-closed — any snapshot rejected by `check_order_book` is excluded, never averaged in. 3 passed.
- **Mutation check:** disabled the reject branch (`if not q.ok:` -> `if False:`) in `summarize_spreads`; `test_summarize_spreads_excludes_rejected_snapshots` + `test_summarize_spreads_all_rejected_reports_no_spread` FAILED red, then reverted to green.

### C. Live collector CLI (`scripts/observe_orderbook.py`)
- **RED:** `tests/test_observe_orderbook.py` written first; `from scripts.observe_orderbook import run_calibration` -> `ModuleNotFoundError`. 2 failed.
- **GREEN:** implemented `run_calibration` (drives `BitgetPublicClient.get_order_book`, gathers N snapshots/symbol, forwards to `summarize_spreads`) + `main()` (argparse, `--symbols` / `--from-manifest`, writes JSON). 2 passed with a fake client (no network, no secrets).

## What this run added / changed
- `src/market/orderbook.py` — NEW: `OrderBook`, `parse_order_book`, `mid_price`, `top_spread_bps`, `depth_within_bps` (fail-closed normalization of public depth).
- `src/market/orderbook_quality.py` — NEW: `check_order_book` fail-closed gate (empty/crossed/non-positive/future/stale).
- `src/market/bitget_public.py` — MODIFIED: adds `orderbook` category + `get_order_book(...)` (read-only `GET /api/v2/mix/market/orderbook`, fail-closed on schema/values).
- `src/market/orderbook_calibration.py` — NEW: `summarize_spreads` fail-closed aggregation.
- `scripts/observe_orderbook.py` — NEW: live collector CLI (read-only public depth).
- `tests/test_order_book.py` (8), `tests/test_orderbook_calibration.py` (3), `tests/test_observe_orderbook.py` (2) — NEW TDD suites.

## Raw tests (executed this run)
```text
pytest tests/test_order_book.py -v              -> 8 passed
pytest tests/test_orderbook_calibration.py -v   -> 3 passed
pytest tests/test_observe_orderbook.py -v       -> 2 passed
python3 -m compileall -q src scripts tests      -> exit 0 (clean)
pytest tests/ -q                                -> 568 passed, 0 failed (full suite, no regressions)
```
(The 568 = the 559 baseline from Phase 35 plus the 9 new tests in this phase; prior untracked order-book tests were already counted. No test was removed. Mutation checks confirmed the fail-closed assertions genuinely bind.)

## Live observed-spread calibration (READ-ONLY public Bitget depth)

Invoked `scripts/observe_orderbook.py --symbols BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,ADAUSDT,AVAXUSDT,SUIUSDT,NEARUSDT --snapshots 3 --limit 20 --interval 0.25`. 24 snapshots fetched, **0 rejected** by the gate. Persisted to `reports/phase-36/orderbook_calibration.json`.

| Symbol | Valid | Spread bps (median) | Mid (USD) | Depth @5bps (contracts) | Depth @60bps (contracts) |
|--------|-------|---------------------|-----------|-------------------------|--------------------------|
| BTCUSDT | 3 | 0.013 | 79,424.75 | 122.0 | 122.0 |
| ETHUSDT | 3 | 0.040 | 2,502.89 | 5,252.6 | 10,045.9 |
| SOLUSDT | 3 | 0.095 | 105.06 | 28,048.6 | 115,272.8 |
| XRPUSDT | 3 | 0.703 | 1.4228 | 1,134,179.3 | 26,366,088.0 |
| ADAUSDT | 3 | 4.797 | 0.20845 | 179,446.0 | 23,722,516.7 |
| AVAXUSDT | 3 | 1.350 | 7.4072 | 3,747.6 | 238,359.7 |
| SUIUSDT | 3 | 1.318 | 0.75865 | 331,353.2 | 7,730,083.2 |
| NEARUSDT | 3 | 1.609 | 1.8641 | 16,739.0 | 1,463,546.7 |

**Honest reading:** observed top-of-book spreads are dramatically tighter than any assumed half-spread for the liquid majors (BTC/ETH/SOL ≈ 0.01–0.1 bps) but materially WIDER than a single global assumption for lower-liquidity alts (ADA ≈ 4.8 bps, AVAX/SUI/NEAR ≈ 1.3–1.6 bps). A cost model that applies one flat assumed spread to every symbol is therefore simultaneously too conservative on majors and too optimistic on alts. The dataset supports moving to a **symbol-specific observed-spread table** rather than a single constant, and re-running cost-stress envelopes per liquidity tier.

## Network calls
- **Unauthenticated public GET `https://api.bitget.com/api/v2/mix/market/orderbook`** with `productType=SUSDT-FUTURES`, `type=step0`, `limit=20`: **24 requests** (8 symbols x 3 snapshots), all HTTP 200, all normalized and passed the gate.
- Rate limiting: `min_interval_seconds=0.25` enforced between requests (client-side throttle in `BitgetPublicClient._get`).
- **No authenticated, signed, or account calls of any kind.** No `DEMO_EXECUTION_CONFIRM`, no live host, no order/fill endpoints touched. Egress confined to the single public orderbook path above.

## Signed calls / orders / positions
- **Signed calls: 0.** Orders: 0. Positions: 0 (open or closed by this phase). This is read-only market-data measurement plus test authoring. No credentials, demo keys, or live keys were used. No signed exchange calls, transfers, withdrawals, or funded execution occurred. No egress beyond the public Bitget market API.

## Trades / fees / funding / PnL
- **Trades executed by this phase: 0.** Fees: 0. Funding: 0 (this phase reads depth only; funding modeling remains in the historical corpus from Phase 35). PnL: 0 (measurement only, no execution). The observed spread is a quoted cost surface, NOT realized PnL.

## Protection / reconciliation
- **Not exercised** by this measurement-only change. The only fail-closed logic is the order-book quality gate (`check_order_book`) which refuses crossed/empty/non-positive/future/stale books before any spread/depth figure enters the calibration. No position, protection, or reconciliation path was touched.

## Limitations (honest)
- **Snapshot, not distribution.** 3 snapshots per symbol is a point-in-time read, not a spread distribution across regimes/volatility. Real execution cost under size also includes slippage beyond the top level and funding — not captured here.
- **`limit=20` under-samples depth for liquid names.** For BTC/ETH the top 20 levels already sit within 5 bps, so `depth_60bps` ≈ `depth_5bps` (the book did not reach the 60 bps band within 20 levels). A deeper `limit` (e.g. 200) is required to measure realistic 60 bps depth on majors; the alt readings are valid because their levels are wider.
- **Spread is quoted, not executed.** The top-of-book spread is the best-case entry/exit cost; actual fills at size will be worse. The table calibrates the *minimum* cost, not the *expected* cost.
- The calibration path is fail-closed on data quality, but `run_calibration` tolerates per-symbol schema/values rejections (a bad symbol is skipped and omitted from the result rather than presented as cheap). It does not abort the whole run.
- Acquired datasets/corpus are git-ignored (`data/history/`); the live calibration JSON is committed as reproducible evidence but is itself regenerable via the same script. No LLM, provider, or autonomous decision path was invoked.

## Phase 6 promotion gate
- **Still BLOCKED.** This phase is purely cost-surface measurement. The deterministic baseline remains negative; no promotion action was taken and none is authorized while the baseline is negative.

## Commit / push
- New/changed: `src/market/orderbook.py`, `src/market/orderbook_quality.py`, `src/market/orderbook_calibration.py`, `src/market/bitget_public.py`, `scripts/observe_orderbook.py`, `tests/test_order_book.py`, `tests/test_orderbook_calibration.py`, `tests/test_observe_orderbook.py`, `reports/phase-36/phase-36-report.md`, `reports/phase-36/orderbook_calibration.json`.
- Git identity verified: `user.name=𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟`, `user.email=42990222+hernanda-git@users.noreply.github.com` (matches `gh api`).
- Secret scan: `.env` is git-ignored; content scan over tracked + new text found **0 secret hits**. Verified repeatable, network-free, secret-free command: `pytest tests/test_order_book.py tests/test_orderbook_calibration.py tests/test_observe_orderbook.py -q`.
