# Phase 16 — Fail-closed per-window walk-forward data-quality gate (unblocked)

**Generated (WIB / Asia/Jakarta):** 2026-08-27 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** evaluation-integrity engineering, offline, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `strengthen walk-forward evaluation` and `data-quality
checks` as unblocked work streams. Today `scripts/evaluate_real_history.py`
performs a **global** `data_quality_report` fail-closed check, but the walk-forward
engine can still train and trade on a window that contains an internal gap or a
bad price. A walk-forward test window is the slice the engine actually trades on,
so a hole inside it silently distorts the few trades within it and can launder a
spurious edge. This is exactly the honest-edge failure mode the earlier phases
guarded against at the report/selection layer; this phase closes it at the data
layer.

This phase adds `src/evaluation/walk_forward_quality.py` (a fail-closed
per-window quality gate) and wires it into `evaluate_real_history.py` so a holey
dataset is rejected **before** any heavy replay (exit code 4), never inventing a
trade. The gate never mutates data, never touches the deterministic promotion
gate, and never emits a promotion/selection/winner flag.

## TDD cycle (strict)

- **RED:** `tests/test_walk_forward_window_quality.py` was written first, importing
  `src.evaluation.walk_forward_quality` (did not exist). Run failed:
  `ModuleNotFoundError: No module named 'src.evaluation.walk_forward_quality'`.
- **GREEN:** Implemented the module (pure slicing + reuse of the existing
  `data_quality_report` and `coverage_gate`). `tests/test_walk_forward_window_quality.py`
  -> 6 passed.
- **REFACTOR:** No refactor needed; the module is a small pure composition of
  existing primitives.

During GREEN a real bug in the first implementation was caught by a test: a gap
*inside* a test window keeps the candle **count** correct (the hole sits between
two present bars), so an exact-bar-count check alone passed it. The guard was
strengthened to also require `len(test_report.gaps) == 0` on every test slice.
After the fix the gap case correctly fails closed.

## Raw tests (executed this run)

```text
pytest tests/test_walk_forward_window_quality.py -v   -> 6 passed
pytest tests/ -q                                     -> 403 passed (no regressions vs 397 + 6 new)
python3 -m compileall -q src scripts tests            -> exit 0 (clean)
```

New tests (6):
- `test_slice_dataset_returns_subdataset_within_range` — slice is inclusive and bounded.
- `test_window_plan_matches_run_walk_forward_indices` — the gate's train/test plan
  lines up exactly with `run_walk_forward`'s index split (cross-checked against the
  real engine), including timestamp mapping back to snapshots.
- `test_clean_dataset_passes_window_quality_gate` — a contiguous dataset passes (all_ok True).
- `test_gap_inside_test_window_fails_closed` — a hole inside a traded window rejects.
- `test_bad_price_inside_test_window_fails_closed` — a non-finite price in a window rejects.
- `test_gate_rejects_before_evaluation_cli_on_window_gap` — the real entrypoint
  returns exit 4 with `WALK_FORWARD_QUALITY_REJECTED` and writes NO report when a
  window contains a gap, proving the heavy replay is skipped.

## Mutation test (assertions are real, not decoration)

Disabled the test-window guard (`test_ok = (...)` -> `test_ok = True`):

```text
pytest tests/test_walk_forward_window_quality.py::test_gap_inside_test_window_fails_closed
pytest tests/test_walk_forward_window_quality.py::test_gate_rejects_before_evaluation_cli_on_window_gap
  -> both FAILED (the guard that should catch the hole was disabled)
pytest tests/test_walk_forward_window_quality.py::test_bad_price_inside_test_window_fails_closed
  -> still failed for the right reason (the bad price also trips the train-window
     structural check), confirming the behavior is independently covered
```

Reverted the mutation -> 6 passed. The mutation broke exactly the assertions that
bind to the test-window guard, proving they test real behavior.

## End-to-end runtime verification (real code paths, no network/credentials)

Wired `gate_walk_forward_dataset(dataset, config)` into `evaluate_real_history.py`
right after the global data-quality check and before the heavy replay. Ran the
real entrypoint on stored datasets (0 network calls):

```text
# TINYUSDT_1m.json (stored, synthetic 150 candles, 5 windows)
EXIT=0   walk-forward window quality ok: failed=0
         net_pnl=109.49  promotion_allowed=false  reason=POSITIVE_EVIDENCE_REQUIRED

# BTCUSDT_1m.json (REAL public history, 2000 candles, 72 walk-forward windows)
EXIT=0   data quality ok: gaps=0 max_missing_bars=0 bad_prices=0 funding_anomalies=0
         walk-forward window quality ok: failed=0 (all 72 windows train_ok/test_ok)
         closed_trades=45  gross_pnl=-1549.50  fees=3543.34  spread=354.33
         slippage=1417.34  funding=7.80  net_pnl=-6872.31
         promotion_allowed=false  reason=NEGATIVE_NET_PNL
```

Both runs emitted `walk_forward_window_quality` in the payload. On real history the
gate passed on all 72 windows (the dataset is genuinely contiguous) and the
deterministic baseline stayed `NEGATIVE_NET_PNL`, so selection remains blocked.

## Network calls

- **0** network requests in the gate module (pure slicing over an in-memory
  `HistoryDataset`). The BTCUSDT end-to-end run used the **stored** dataset
  (no `--fetch`), so `request_evidence`: requests=0, successes=0, failures=0,
  rate_limits=0, retries=0, schema_rejections=0, policy_rejections=0,
  signed_calls=0, orders=0, credentials_used=False. The only venue product
  referenced anywhere is `SUSDT-FUTURES` (public unauthenticated history), never
  `USDT-FUTURES`.

## Signed calls / orders / positions

- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed by this phase). This
  is evaluation-integrity engineering only. No credentials, demo keys, or live
  keys were used. No signed exchange calls, transfers, withdrawals, or funded
  execution occurred.

## Trades / fees / funding / PnL

- No trades were opened or closed by this phase. The numbers above
  (`closed_trades=45`, `net_pnl=-6872.31`, `fees=3543.34`, `funding=7.80` for
  BTCUSDT) are produced by the cost-inclusive deterministic replay engine over the
  stored real-history series; they are measurement facts, not realized PnL, and
  remain negative. The gate performs no trading, fee, funding, or PnL computation
  of its own; it only checks window integrity.

## Protection / reconciliation

- Not exercised by this phase (no positions were created), consistent with it
  being evaluation-only. Protection supervision and reconciliation read-back
  remain covered by their own suites, which are part of the 403 passing tests.
  The gate runs orthogonally and never touches runtime trading state.

## Limitations (honest)

- The gate checks each window slice for structural soundness (`ok`), exact test
  bar count, and zero internal gaps. It reuses the existing `coverage_gate` (with
  `max_missing_fraction`, default 0.25) on **training** slices only; training
  sparseness is tolerated while test windows must be gap-free. A future caller who
  wants stricter training tolerances can pass a smaller `max_missing_fraction`.
- Freshness (`max_data_age_ms`) is intentionally **not** applied per-window: the
  dataset shares one `fetched_at_ms`, and a per-slice age would falsely fail
  earlier windows. Freshness stays a dataset-level concern already handled by the
  global `data_quality_report` check in the entrypoint.
- The gate validates the *candle series* only. It does not re-validate the derived
  `MarketSnapshot` indicators (which `run_walk_forward` already validates via
  `_validate_replay_snapshots`). A dataset that passes the global check but has a
  malformed derived snapshot would still be caught downstream by that validator.
- `evaluate_real_history.py` does not invoke `assert_truthful` (the report-honesty
  guard wired in phase 15 into `run_strategy_baseline`). Its fail-closed story is
  the explicit exit-code contract (2 = bad prices, 3 = funding coverage, 4 = window
  quality). For full dashboard-truthfulness parity, wiring `assert_truthful` into
  this entrypoint is a recommended follow-up, not done here.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. The new gate additionally guarantees the walk-forward
engine can never train or trade on a holey or corrupted window, strengthening the
honest-edge surface without altering the deterministic gate. Unblocked research/
engineering continues per the cron mandate.
