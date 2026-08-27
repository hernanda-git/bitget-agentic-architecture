# Phase 25 — Strategy attribution: honest decomposition of measured per-strategy returns (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-28 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline evaluation-engineering (measurement only), no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `strategy attribution` as an explicitly unblocked research/engineering
stream alongside walk-forward, cost/funding/slippage stress, and data-quality. The repository
already has strong robustness measurement (`cscv`, `walk_forward_strength` DSR/Holm,
`multisymbol` per-symbol aggregation, `statistics` per-parameter stability), but it has **no
module that decomposes an already-measured set of candidate strategy return series into
per-family contribution + dispersion**. That is the gap this phase closes.

New file: `src/evaluation/attribution.py` (`attribute_performance`).
New test file: `tests/test_attribution.py` (13 tests).

Design (fail-closed, descriptive-only by construction):
- `selection_blocked` is always `True`; the report never emits a `winner` / `promotion_allowed`
  / `selection` flag, so it cannot change the Phase 6 deterministic promotion gate (which stays
  `NEGATIVE_NET_PNL` / blocked).
- Per-family contribution: `n`, `expectancy`, bootstrap `bootstrap_ci`, `sharpe` (sample std,
  `None` when degenerate), `net_total`, `abs_total`, `share_of_net`, `evidence_status`.
- A clearly-labelled `blend` (equal-weight, aligned to the shortest series) with bootstrap CI,
  tagged `is_descriptive=True` and `selection_blocked=True`. It is NOT a recommended allocation
  and NOT a selection signal.
- `cross_sectional` dispersion: `top_abs_contributor`, `top_abs_share`, `net_positive_count`,
  `net_negative_count`, `dominant_net_contributor` (by abs net, descriptive only).
- Reuses `bootstrap_ci` from `src.evaluation.statistics` so uncertainty matches the rest of the stack.
- Fail-closed preconditions raise `ValueError`: fewer than 2 families, any empty series, any
  non-finite value. `share_of_net` is `None` (no crash) when net cancels to zero.

## Resource guard (run at start of every run)

```text
python3 scripts/resource_guard.py --json
  ok: true
  violations: []
  disk_used_percent: 45.60 (< policy max 85.0)
  swap_used_percent: 82.14 (< policy max 90.0)
  available_memory_bytes: 1682292736
  inode_free_percent: 50.13
```

GREEN, so the full heavy regression suite was permitted as the regression gate.

## TDD cycle (strict, vertical slice)

### RED (module missing)

New file `tests/test_attribution.py`. Run before the implementation existed:

```text
.venv/bin/python -m pytest tests/test_attribution.py -q
  ERROR collecting tests/test_attribution.py
    ImportError while importing test module .../test_attribution.py
  E   ModuleNotFoundError: No module named 'src.evaluation.attribution'
```

Fails for the correct reason: the feature is missing, not a typo.

### GREEN (minimal code)

`src/evaluation/attribution.py` implements `attribute_performance` with the contract above.
First GREEN run:

```text
.venv/bin/python -m pytest tests/test_attribution.py -v
  13 passed in 7.97s
```

### REFACTOR

No duplication remained: the per-family CI and the blend CI both flow through the existing
`bootstrap_ci`, and the concentration / dispersion math is a single pass. No behavior change.

## Raw tests (executed this run)

```text
# New phase-25 suite (GREEN):
.venv/bin/python -m pytest tests/test_attribution.py -v
  13 passed in 7.97s

# Full project regression gate (GREEN, resource guard permitted heavy run):
.venv/bin/python -m pytest tests/ -q
  474 passed in 213.07s   (was 461; +13 new)

# Compileall (whole tree, clean):
.venv/bin/python -m compileall -q src
  -> exit 0 (clean)
```

Per-test results (focused suite):
- test_module_and_function_exist — PASS
- test_requires_at_least_two_strategies — PASS
- test_empty_series_raises — PASS
- test_non_finite_raises — PASS
- test_per_strategy_expectancy_and_ci_bounds — PASS
- test_not_evidenced_below_min_samples — PASS
- test_share_of_net_sums_to_one_when_positive — PASS
- test_zero_total_net_avoids_division_by_zero — PASS
- test_blend_is_descriptive_and_blocked — PASS
- test_concentration_top_abs_share — PASS
- test_deterministic_ordering — PASS
- test_reproducible_ci_same_seed — PASS
- test_real_shaped_local_history_does_not_select — PASS

## Mutation check (assertions bind to real logic, not decoration)

Per build-verification, a suite that cannot fail is the same trap as a flat-line metric.
Backed up `src/evaluation/attribution.py`, disabled the concentration detector
(`top_abs_share = (strategies[top_abs_name]["abs_total"] / total_abs) if total_abs > 0 else 0.0`
-> `top_abs_share = 0.0 if total_abs > 0 else 0.0`), ran the phase-25 suite, then restored.

```text
# under mutation (concentration disabled):
.venv/bin/python -m pytest tests/test_attribution.py::test_concentration_top_abs_share -q
  1 failed
  FAILED test_concentration_top_abs_share
    assert 0.0 == 0.9090909090909091

# restored:
.venv/bin/python -m pytest tests/test_attribution.py -q
  13 passed in 12.85s
  diff against backup: NO DIFF (clean restore)
```

The exact concentration assertion fails under mutation and passes when restored, proving it
binds to the new logic. The other 12 assertions stay green under this mutation because they
exercise non-mutated paths.

## Network calls / signed calls / orders / positions

- **Network calls: 0.** No public Bitget acquisition occurred this run. The real-shaped test
  (`test_real_shaped_local_history_does_not_select`) reads the already-local
  `data/history/BTCUSDT_1m.json` (public data acquired by an earlier phase), so it exercises
  real-shaped inputs without any network egress.
- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed). No credentials, demo keys, or
  live keys were used. No signed exchange calls, transfers, withdrawals, or funded execution
  occurred. The change is pure offline evaluation math over in-process lists and local files.

## Trades / fees / funding / PnL

No trades, fees, funding, or realized PnL were produced. This phase is a descriptive
decomposition of already-measured return series; it touches no market simulation or PnL path.
The 474 passing tests include the existing cost/funding/slippage stress, walk-forward
DSR/Holm, CSCV, and data-quality suites, which remain green and unmodified by this change.

## Protection / reconciliation (unaffected, noted for completeness)

This phase does not alter the protection supervisor or reconciliation engine (strengthened in
earlier phases, most recently the fail-closed wrong-side-stop read-back in phase 23, and CSCV
in phase 24). Attribution is an offline evaluation artifact consumed by the research/attribution
path; it has no execution, protection, or reconciliation side effects and carries
`selection_blocked=True` so it cannot influence any live decision.

## Limitations (honest)

- Attribution is **descriptive, not causal**. A family with the largest `abs_total` contribution
  is not necessarily the "best" strategy; it may simply be the most volatile. `top_abs_share`
  measures concentration of magnitude, not edge quality. Read it alongside `expectancy`,
  `bootstrap_ci`, `sharpe`, and the CSCV/DSR robustness metrics.
- `blend` is an equal-weight, shortest-series-aligned descriptive summary. It is deliberately
  NOT a portfolio recommendation and must never feed the promotion gate (guarded by
  `selection_blocked=True` on the blend too).
- `sharpe` uses a sample standard deviation and is `None` when the series is constant or `n < 2`;
  it is a naive per-step Sharpe of the supplied returns, not a risk-adjusted portfolio Sharpe.
- The real-history illustration uses two simple momentum return families derived from one local
  BTC 1m file as a *demo of the wiring*, not an evaluated strategy set. Its numbers are a
  property of that specific synthetic construction on that slice, not a claim about any deployed
  strategy.
- The full 474-test suite was run once and passed (~213s CPU); it is the project's verification
  gate. The bootstrap CI is seed-fixed for reproducibility but its width depends on `bootstrap_samples`.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. This phase strengthens the **strategy attribution** unblocked stream
and adds no selection, LLM, or execution path. Unblocked research/engineering continues per the
cron mandate.

## Commit / publish evidence

- Committed as `c5f3d32` with gh-derived identity `𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟 <42990222+hernanda-git@users.noreply.github.com>`.
- Pushed to `origin/master` (`0044111..c5f3d32`).
- Content-level secret scan over tracked + untracked text: **0 hits**.
- `.env` confirmed git-ignored; post-push tree scan for sensitive filenames: **CLEAN** (no
  `.secrets` / `private_key` / `config.json` / `.env` / `burner` in the published tree).
- Repo remains public (`isPrivate: false`) as required by the standing mandate.
