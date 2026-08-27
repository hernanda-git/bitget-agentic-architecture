# Phase 24 — Walk-forward overfitting guard: CSCV Probability of Backtest Overfitting (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-28 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline evaluation-engineering (measurement only), no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `strengthen walk-forward evaluation`, `strategy attribution`, and
`data-quality checks` as unblocked streams. The existing honest-edge walk-forward guard
(`src/evaluation/walk_forward_strength.py`) already applies a per-window Holm correction and
a Deflated Sharpe Ratio (DSR), but neither answers the overfitting question directly:
**does the train-best configuration actually generalize out-of-sample?** DSR discounts a
Sharpe by trials/skew/kurtosis; Holm corrects across windows. Neither measures rank stability
between a train partition and a held-out test partition.

This phase adds the standard companion metric, **Combinatorial Symmetric Cross-Validation
(CSCV) Probability of Backtest Overfitting** (Bailey & Lopez de Prado, 2014):

- Partition each strategy's per-block performance series into `S` blocks.
- Exhaustively (or sampled) split the `S` blocks into train/test halves.
- Within each split, rank strategies by train performance and by test performance.
- `pbo` = fraction of splits where the train-best strategy lands in the bottom half
  out-of-sample (relative rank > N/2). High `pbo` => overfit.
- `mean_r` / `mean_r_squared` = mean (signed / squared) Pearson correlation between train
  ranks and test ranks. Positive => rank-stable / generalizes; negative => anti-generalizes.

This directly strengthens walk-forward robustness evidence and is measurement-only: the
result always carries `selection_blocked=True` and never emits a promotion / selection /
winner flag, so it cannot change the Phase 6 deterministic promotion gate (which stays
`NEGATIVE_NET_PNL` / blocked).

New file: `src/evaluation/cscv.py` (with `cscv_pbo` and `performance_matrix_from_returns`).
New test file: `tests/test_cscv_pbo.py` (15 tests).

## Resource guard (run at start of every run)

```text
python3 scripts/resource_guard.py --json
  ok: true
  violations: []
  disk_used_percent: 45.59 (< policy max 85.0)
  swap_used_percent: 83.67 (< policy max 90.0)
  available_memory_bytes: 1709813760
  inode_free_percent: 50.14
```

GREEN, so the full heavy suite was permitted as the regression gate.

## TDD cycle (strict, vertical slice)

### RED (module missing)

New file `tests/test_cscv_pbo.py`. Run before the implementation existed:

```text
pytest tests/test_cscv_pbo.py -q
  ERROR collecting tests/test_cscv_pbo.py
    ModuleNotFoundError: No module named 'src.evaluation.cscv'
```

Fails for the correct reason: the feature is missing, not a typo.

### GREEN (minimal code)

`src/evaluation/cscv.py` implements `cscv_pbo` (rank-based PBO + signed/squared Pearson R
over train/test rank vectors) and `performance_matrix_from_returns` (chops per-strategy
return series into blocks, computes per-block Sharpe/mean). Fail-closed preconditions:
`<2` strategies, `<4` or odd blocks, ragged rows, and non-finite values all raise `ValueError`.

First GREEN run exposed a real rank-direction bug: `_rank_desc` assigns rank 1 to the
*highest* value, but the draft `best_idx` used `max`, which selected the *worst* strategy.
Selecting the *minimum* rank fixed it. After the fix:

```text
pytest tests/test_cscv_pbo.py -v
  15 passed in 0.06s
```

### REFACTOR

Extracted a single `_pearson_r` (signed) helper; `mean_r_squared` is `r*r`, so both signed and
squared views are reported without duplicated correlation math. No behavior change.

## Raw tests (executed this run)

```text
# New phase-24 suite (GREEN):
.venv/bin/python -m pytest tests/test_cscv_pbo.py -v
  15 passed in 0.06s

# Full project regression gate (GREEN, resource guard permitted heavy run):
.venv/bin/python -m pytest tests/ -q
  461 passed in 199.74s   (was 446; +15 new)

# Compileall (whole tree, clean):
.venv/bin/python -m compileall -q src scripts tests
  -> exit 0 (clean)
```

Actual metric values observed (documented, not asserted away):

```text
# Constructed controls:
robust  (constant per strategy) : pbo=0.0,  mean_r=+1.00, mean_r_squared=1.00, risk=LOW
overfit (fold specialist, +1 in own block only):
                                : pbo=1.0,  mean_r=-1.00, mean_r_squared=1.00, risk=HIGH

# Real local history (no network): 6 BTCUSDT momentum families, lookbacks 3/5/8/13/21/34,
# 2466 returns, 6 blocks of 411, per-block Sharpe:
cscv_pbo(real BTCUSDT momentum families):
  n_strategies=6, n_blocks=6, combinations=20,
  pbo=0.6, mean_r=-0.371, mean_r_squared=0.610, overfit_risk=HIGH, selection_blocked=True
```

The real-history read is an honest, useful finding: the naive momentum parameter families are
rank-unstable on this BTC history slice (train-best generalized poorly; `pbo=0.6` => HIGH
overfit risk). It is reported as measurement only and does NOT unblock selection.

## Mutation check (assertions bind to real logic, not decoration)

Per build-verification, a suite that cannot fail is the same trap as a flat-line metric.
Backed up `src/evaluation/cscv.py`, disabled the overfit detector (`if relative_rank >
n_strategies / 2.0:` -> `if False:`), ran the phase-24 suite, then restored.

```text
# under mutation (PBO guard disabled):
.venv/bin/python -m pytest tests/test_cscv_pbo.py -q
  1 failed, 14 passed
  FAILED test_overfit_fold_specialist_yields_high_pbo
    assert 0.0 > 0.5   (pbo collapsed to 0.0)
# restored:
  15 passed in 0.04s
```

The exact overfit-detection assertion fails under mutation and passes when restored, proving
it binds to the new logic. (The robust/invariant assertions correctly stay green under this
mutation because they exercise the non-mutated paths.)

## Network calls / signed calls / orders / positions

- **Network calls: 0.** No public Bitget acquisition occurred this run. The real-history test
  reads the already-local `data/history/BTCUSDT_1m.json` (public data acquired by an earlier
  phase), so it exercises real-shaped inputs without any network egress.
- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed). No credentials, demo keys, or
  live keys were used. No signed exchange calls, transfers, withdrawals, or funded execution
  occurred. The change is pure offline evaluation math over in-process lists and local files.

## Trades / fees / funding / PnL

No trades, fees, funding, or realized PnL were produced. This phase is a correctness
strengthening of walk-forward robustness measurement; it touches no market simulation or PnL
path. The 461 passing tests include the existing cost/funding/slippage stress, walk-forward
DSR/Holm, and data-quality suites, which remain green and unmodified by this change.

## Protection / reconciliation (unaffected, noted for completeness)

This phase does not alter the protection supervisor or reconciliation engine (strengthened in
earlier phases, most recently the fail-closed wrong-side-stop read-back in phase 23). CSCV is
an offline evaluation metric consumed by the research/attribution path; it has no execution,
protection, or reconciliation side effects.

## Limitations (honest)

- CSCV measures **rank stability**, not economic significance. A configuration family can be
  rank-stable (`pbo` low) yet still have negative expected net PnL after costs; CSCV must be
  read alongside DSR, Holm, and the fee-inclusive expectancy/CI, not instead of them. It never
  feeds the promotion gate.
- `pbo` uses a strict "bottom half" rule (relative rank > N/2). For small `N` the threshold is
  coarse; with `N=6` the band is 3 of 6. Larger candidate families give a finer read and are
  recommended before any promotion discussion (which remains blocked).
- The metric requires `S >= 4` even blocks. For short replay streams this caps the number of
  folds; `performance_matrix_from_returns` requires each series length to be exactly divisible
  by `block_size` (fail-closed), so callers must choose a block size that tiles the stream.
- The real-history illustration uses simple momentum return series derived from one local BTC
  1m file as a *demo of the wiring*, not an evaluated strategy family. Its `pbo=0.6` is a
  property of that specific synthetic family on that slice, not a claim about any deployed
  strategy.
- The full 461-test suite was run once and passed (~200s CPU); it is the project's verification
  gate.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. This phase strengthens walk-forward overfitting detection (an
unblocked stream) and adds no selection, LLM, or execution path. Unblocked research/engineering
continues per the cron mandate.
