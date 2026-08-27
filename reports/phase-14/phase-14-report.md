# Phase 14 — Honest-edge walk-forward strengthening (Holm + Deflated Sharpe), measurement only (unblocked)

**Generated (WIB / Asia/Jakarta):** 2026-08-27 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** evaluation-quality engineering, offline, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists "strengthen walk-forward evaluation" as an unblocked research
stream. The existing walk-forward pipeline (`src/evaluation/baseline.py`) already
reports aggregate net PnL and a window-level bootstrap CI plus a Bonferroni-style
robustness gate, but it has two honest-edge gaps:

1. **Per-window multiple testing.** It never asks how many INDIVIDUAL walk-forward
   windows survive a multiple-testing correction. A strategy can aggregate to a
   positive point estimate because ONE lucky window landed well. We add a per-window
   one-sided bootstrap test (mean trade PnL <= 0) and a Holm step-down correction
   across windows.
2. **Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2012).** A high Sharpe is easy
   to manufacture under multiple testing and non-Normal trade returns. The DSR
   discounts the observed Sharpe by the number of trials and by the trade
   distribution's skew/kurtosis, answering P(observed SR > false-discovery SR).

To feed (1) we first extended `run_walk_forward` to attach the per-window trade PnL
list (`trade_pnls`) to each window row. Each PnL is cost-aware:
`gross_pnl - entry_fee - exit_fee - spread - slippage - funding`
(`src/evaluation/baseline.py:175`).

Every entry point keeps `selection_blocked` True and never emits `promoted` /
`selected` / `winner` keys, so it stays compatible with the always-blocked Phase 6
deterministic promotion gate (`NEGATIVE_NET_PNL`).

## TDD cycle (strict)

- **RED:** `tests/test_walk_forward_strength.py` was written first, importing
  `window_one_sided_p`, `holm_stepdown`, `deflated_sharpe`, `strengthen_walk_forward`
  (none existed) and asserting `run_walk_forward` rows carry `trade_pnls`. Run failed
  (`ModuleNotFoundError` / missing `trade_pnls` key).
- **GREEN:** Implemented `src/evaluation/walk_forward_strength.py` and extended
  `baseline.py` to carry `trade_pnls`. `tests/test_walk_forward_strength.py` -> 16 passed.
- No refactor needed; functions are small and pure.

## Raw tests (executed this run)

```text
pytest tests/test_walk_forward_strength.py -v            -> 16 passed
pytest tests/ -q                                         -> 380 passed  (no regressions vs 364 + 16 new)
python3 -m compileall -q src scripts tests               -> exit 0 (clean)
```

Coverage (16 tests):
- `run_walk_forward` attaches a `trade_pnls` list to every window row (RED before impl).
- `window_one_sided_p`: rejects a clearly positive window (p < 0.05), keeps the null for
  a negative window (p > 0.5), is deterministic given a seed, fails closed on empty.
- `holm_stepdown`: rejects only the strongly-significant window when others are large,
  rejects none when all large, respects `alpha` in the step-down threshold.
- `deflated_sharpe`: low DSR for zero-mean high-variance (no edge), DSR=1.0 for
  degenerate consistent-positive (no uncertainty), fails closed on <2 observations, and
  `expected_false_sharpe` grows with `trials`.
- `strengthen_walk_forward`: never promotes (no `promoted`/`selected`/`winner` keys,
  `selection_blocked` True), reports all components, fails closed without adequate
  sample, consumes real walk-forward rows, and rejects empty rows fail-closed.

## Mutation test (assertions are real, not decoration)

Forced `robust_edge = True` (backup restored afterward):

```text
pytest tests/test_walk_forward_strength.py -q
  FAILED test_strengthen_fails_closed_without_adequate_sample
  1 failed, 15 passed    <- exactly the robust-edge assertion went red
```

Restored the file -> 16 passed. The mutation broke ONLY the test that asserts the
fail-closed `robust_edge=False` under an inadequate sample, proving the assertion binds
to the real guard.

## End-to-end runtime verification (real code paths, no network/credentials)

Ran `strengthen_walk_forward` over real `run_walk_forward` rows built from the synthetic
baseline series (`scripts/run_strategy_baseline.make_series(50)`):

```text
windows: 1  with_trades: 1
holm_surviving: 0  dsr_positive: False  robust_edge: False
selection_blocked: True
adequate_sample: False  total_closed_trades: 5
OK: honest-edge guard ran on real walk-forward rows; selection_blocked True
```

Behavior is correct fail-closed: the synthetic series produces only 5 closed trades
(< `min_closed_trades=30`), so `adequate_sample=False` and `robust_edge=False`. No
promotion, no winner flag. The same guard is exercised on stored public datasets by
`run_strategy_baseline` / `evaluate_real_history` without any selection output.

## Network calls

- **0** network requests. The module is pure math over in-memory trade-PnL lists. No
  `--fetch`, no signed calls, no live/demo credentials. `request_evidence`:
  requests=0, successes=0, failures=0, rate_limits=0, retries=0, schema_rejections=0,
  policy_rejections=0, signed_calls=0, orders=0, credentials_used=False.

## Signed calls / orders / positions

- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed by this phase). This is
  evaluation-quality engineering only. No credentials, demo keys, or live keys were
  used. The only venue product referenced anywhere is `SUSDT-FUTURES` (public
  unauthenticated history), never `USDT-FUTURES`.

## Trades / fees / funding / PnL

- No trades opened or closed by this phase. The `trade_pnls` consumed by the guard are
  produced by the cost-inclusive deterministic replay engine over previously-acquired
  public history; they are measurement inputs, not realized PnL, and the aggregate
  remains negative. `walk_forward_strength` performs no trading, fee, funding, or PnL
  computation of its own; it only summarizes the already-costed PnL stream.

## Protection / reconciliation

- Not exercised by this phase (no positions were created), consistent with it being
  evaluation-only. Protection supervision and reconciliation read-back remain covered by
  their own suites, which are part of the 380 passing tests. The guard runs
  orthogonally to protection/reconciliation and never touches runtime trading state.

## Limitations (honest)

- `window_one_sided_p` is a bootstrap with a fixed `samples=2000` and `seed`; its p-value
  is an estimate (deterministic given seed) and converges with `samples`. Increasing
  `samples` tightens the estimate at CPU cost.
- Holm correction assumes the windows are independent simultaneous tests. Walk-forward
  windows overlap in time by construction, so the independence assumption is
  conservative-ish; the guard is a descriptive honesty check, not a proof of edge, and
  never feeds the promotion gate.
- DSR uses the standard Normal approximation for the probability integral; it is a
  well-known heuristic (Bailey & Lopez de Prado, 2012) and is fail-closed: a
  non-positive denominator forces `dsr_prob=0`.
- The verdict `robust_edge` is descriptive and measurement-only. It does NOT change the
  deterministic `NEGATIVE_NET_PNL` gate; selection stays blocked regardless of its value.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. Unblocked research/engineering (walk-forward honesty) continues
per the cron mandate.
