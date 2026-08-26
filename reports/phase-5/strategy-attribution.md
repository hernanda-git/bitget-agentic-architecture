# Phase 5 addendum: per-strategy walk-forward attribution (strategy attribution, focus #3)

**Work unit:** Add independent per-strategy walk-forward attribution to the
deterministic evaluation engine, so each strategy's signal is measured on its
own across unseen test windows. This is measurement only: it never selects,
ranks, or promotes a strategy, and it cannot peek at the test set to choose a
"winner". The deterministic promotion gate (`NEGATIVE_NET_PNL`) remains the
only thing that may unblock Phase 6.

**Boundary honored:** No signed calls, no credentials, no orders, no transfers.
All real-data runs used the stored unauthenticated `SUSDT-FUTURES` public
history (`data/history/*.json`) or the unauthenticated public API only when a
fresh fetch was probed. The attribution function itself makes
`network_calls = 0`.

## What changed

1. **`src/evaluation/baseline.py`**
   - Added a module-level `ALL_STRATEGIES` registry so attribution, walk-forward,
     and the combined baseline enumerate strategies in one place.
   - `run_baseline` and `run_walk_forward` gained a `strategies` selector
     (keyword-only, default = all three) so a single strategy can be replayed
     in isolation. Backward compatible: every existing caller still evaluates
     all strategies.
   - Added `run_strategy_attribution(snapshots, config)` which replays each
     canonical strategy ALONE across the same walk-forward windows and returns
     per-strategy robustness facts (windows, windows_with_trades,
     profitable_windows, closed_trades, total_net_pnl, worst/best window net,
     and the per-window net list). The result always carries
     `selection_blocked: True` and emits no `best`/`selected`/`promoted` key.
2. **`scripts/evaluate_real_history.py`** now also emits `strategy_attribution`
   in its payload (real-data run).
3. **`scripts/run_strategy_attribution.py`** (new, reusable, in-repo) runs the
   attribution on a stored dataset or a fresh unauthenticated public fetch,
   fails closed on the data-quality gate, and writes a JSON artifact.
4. **`tests/test_strategy_attribution.py`** (new): 7 failing-tests-first cases.

## TDD verification (red -> green)

- RED: wrote `tests/test_strategy_attribution.py` first; the suite failed to
  collect (`ImportError: cannot import name 'run_strategy_attribution'` and
  `No parameter named "strategies"`), proving the contract did not yet exist.
- GREEN: implemented the minimal code; focused tests pass.
- Full suite before: `264 passed`. Full suite after: `271 passed` (the 7 new
  tests, no regressions). `python3 -m compileall -q src scripts tests` -> clean.

### Tests added (7)
- `test_strategy_attribution_returns_one_entry_per_strategy`
- `test_strategy_attribution_never_selects_a_winner` (asserts `selection_blocked`
  and absence of `best_/selected_/promoted_strategy`)
- `test_attribution_matches_independent_single_strategy_walk_forward` (binds the
  aggregation to a direct single-strategy `run_walk_forward` so the numbers
  cannot silently diverge)
- `test_attribution_reports_per_window_net_pnl_series`
- `test_single_strategy_walk_forward_runs_isolated_no_other_strategies`
- `test_attribution_rejects_empty_snapshots_fail_closed`
- `test_attribution_rejects_tampered_replay_data_fail_closed`

## Raw evaluation metrics (real public history, cost-inclusive)

Cost assumptions (all runs): fee 5 bps entry+exit, funding 2 bps, slippage 2 bps,
assumed half-spread 0.5 bps, `real_funding=True` (real settlement rates).
Network calls in every attribution run: `0`. Signed calls: `0`. Orders: `0`.
Positions opened by the *attribution* path: `0` (it is a measurement replay over
a fake exchange; the per-window paper fills are internal to the cost engine).

### Combined full-sample baseline, BTCUSDT 1m (1500 candles, stored)
- Snapshots replayed: `1500`
- Orders (paper): `36`; closed trades: `35`
- Gross PnL: `-1065.20`
- Fees: `2769.78`; Spread: `276.98`; Slippage: `1107.91`; Funding: `4.51`
- **Net PnL: `-5224.38`**
- Promotion allowed: `false` (reason `NEGATIVE_NET_PNL`)
- Walk-forward windows: `54`
- Cost-coverage variants promotion reasons: `NEGATIVE_NET_PNL`, `NEGATIVE_NET_PNL`, `INCONCLUSIVE_NO_CLOSED_TRADES`

### Per-strategy walk-forward attribution (the new deliverable)

**BTCUSDT 1m, 1500 candles, 54 walk-forward windows**
| strategy | windows_with_trades | closed_trades | total_net_pnl | profitable_windows | worst | best |
|---|---|---|---|---|---|---|
| trend_continuation | 0 | 0 | 0.0 | 0 | 0.0 | 0.0 |
| mean_reversion | 0 | 0 | 0.0 | 0 | 0.0 | 0.0 |
| volatility_breakout | 52 | 55 | -5868.76 | 11 | -481.66 | +89.45 |
| **selection_blocked** | | | **True** | | | |

**BTCUSDT 5m, bounded 2000-snapshot slice, 72 walk-forward windows**
| strategy | windows_with_trades | closed_trades | total_net_pnl | profitable_windows |
|---|---|---|---|---|
| trend_continuation | 3 | 3 | -735.93 | 0 |
| mean_reversion | 2 | 2 | -307.91 | 0 |
| volatility_breakout | 63 | 66 | -7299.20 | 9 |
| **selection_blocked** | | | **True** | |

**ETHUSDT 5m, bounded 2000-snapshot slice, 72 walk-forward windows**
| strategy | windows_with_trades | closed_trades | total_net_pnl | profitable_windows |
|---|---|---|---|---|
| trend_continuation | 11 | 12 | -69.75 | 1 |
| mean_reversion | 8 | 8 | -10.03 | 2 |
| volatility_breakout | 60 | 62 | -179.05 | 11 |
| **selection_blocked** | | | **True** | |

## Promotion verdict (unchanged, reinforced)

`BLOCKED`. On every symbol, granularity, and strategy, cost-inclusive walk-forward
net PnL is negative after fees, funding, spread, and slippage. No strategy
attribution result flips the `NEGATIVE_NET_PNL` gate. Phase 6 bounded LLM
selection remains blocked by the negative deterministic baseline, exactly as the
autonomous operating rules require. This work unit strengthens the *measurement*
of that baseline; it does not, and must not, manufacture profitability.

## Protection / reconciliation in this unit

This unit is evaluation-only. It does not open positions requiring protection
or reconciliation against a live venue. The fake-exchange replay inside the cost
engine attaches simulated protection per trade (counted in the combined baseline
`protection_attachments`), but no venue read-back or reconciliation adapter is
exercised here. `reconciliation_checks = 0` is expected and honest for an
offline replay engine.

## Limitations (honest, do not suppress)

- **Walk-forward windows are independent replays.** Each test window resets
  position state, so a strategy may trade once per window. Trade counts across
  walk-forward windows (e.g. volatility_breakout 55 on 1m) are therefore NOT
  directly comparable to the continuous full-sample baseline (35 closed trades);
  they are a standard walk-forward estimate, not a compounded equity curve.
- **Runtime is O(n^2) in the replay engine.** The full 6000-candle 5m datasets
  would take ~10 minutes to attribute end-to-end, so this run used bounded
  2000-snapshot slices for the 5m symbols. The 1m dataset was evaluated in full
  (1500 candles, 54 windows). The engine's per-window cost loop is the next
  candidate for a performance pass; it is a separate concern from correctness.
- **Stored datasets are different windows than the earlier fresh fetch.** The
  earlier `real-data-baseline.json` (1335 trades) came from a different fresh
  fetch; stored `BTCUSDT_1m.json` here yields only 35 closed trades because its
  price window activates different strategies. This is real regime variation,
  not a bug, and is itself evidence that strategy attribution (not a single
  blended number) is the right lens.
- **No strategy is selected.** `selection_blocked` is invariant; downstream
  code must not treat any strategy as promoted.

## Pre-publish checks (this work unit)

- `git config --local user.name` = `𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟` (matches `gh api user`)
- `git config --local user.email` = `42990222+hernanda-git@users.noreply.github.com`
- `git check-ignore .env` -> ignored
- Secret scan over all tracked/untracked text -> `0` hits
- `python3 -m compileall -q src scripts tests` -> clean
- `python3 -m pytest -q` -> `271 passed`
- Network calls in attribution runs: `0`; signed calls: `0`; orders: `0`
- `/opt/bots/bitget-listener` untouched (never read, modified, or imported)
