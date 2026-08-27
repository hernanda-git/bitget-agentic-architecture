# Phase 26 — Cost sensitivity envelope: full independent fee/funding/slippage grid (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-28 04:06 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline evaluation-engineering (measurement only), no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate explicitly unblocks `realistic cost/funding/slippage stress` and
`data-quality checks`. The standing strategy review (full-review P2-5) flagged that
historical execution cost assumptions remain incomplete and asked to *"run a range of
spread/latency/partial-fill stress scenarios and report the full sensitivity
envelope."*

The existing cost-stress stack does **not** report a full envelope:

- `cost_sensitivity_sweep` / `run_cost_stress` scale ALL three costs together by a
  single ladder multiplier.
- `run_stress_matrix` / `run_combined_stress` raise costs one dimension at a time (or
  as a single combined point).

None sweeps the **independent** combinations of fee / funding / slippage as a grid and
reports the envelope (min / max / median net PnL + worst / best cell). Phase 26 closes
that gap with `cost_envelope_sweep`.

New implementation: `cost_envelope_sweep` in `src/evaluation/cost_sensitivity.py`.
New test file: `tests/test_cost_envelope.py` (9 tests).
New report script: `scripts/run_cost_envelope_report.py` (honest envelope report).

Design (fail-closed, descriptive-only by construction):
- Sweeps the Cartesian product of the three cost ladders; each cell replays the same
  cost-inclusive baseline engine with that cell's scaled `fee_bps / funding_bps /
  slippage_bps`.
- Reports `min_net`, `max_net`, `median_net`, `worst_cell`, `best_cell`, and
  `n_cells`, plus per-cell cost fields and `drawdown`.
- `selection_blocked` is always `True` and `promotion_blocked` is always `True`; no
  `winner` / `promoted` / `selected` / `go_live` / `positive_edge` key is ever emitted,
  so the Phase 6 deterministic promotion gate (`NEGATIVE_NET_PNL`) stays blocked.
- Fail-closed preconditions raise `ValueError`: empty snapshots, any non-finite or
  negative multiplier. A stress cell may **never** invent trades versus baseline
  (`closed_trades <= baseline.closed_trades`), else `AssertionError`.

## Resource guard (run at start of every run)

```text
python3 scripts/resource_guard.py --json
  ok: true
  violations: []
  disk_used_percent: 45.60 (< policy max 85.0)
  swap_used_percent: 81.83 (< policy max 90.0)
  available_memory_bytes: 1676607488
  inode_free_percent: 50.13
```

GREEN, so the full heavy regression suite was permitted as the regression gate.

## TDD cycle (strict, vertical slice)

### RED (function missing)

New file `tests/test_cost_envelope.py`. Run before the implementation existed:

```text
.venv/bin/python -m pytest tests/test_cost_envelope.py -q
  FAILED tests/test_cost_envelope.py::test_module_and_function_exist - AssertionError
  FAILED tests/test_cost_envelope.py::test_rejects_empty_snapshots - ImportError
    E  ImportError: cannot import name 'cost_envelope_sweep' from 'src.evaluation.cost_sensitivity'
  ... (9 failed)
  9 failed in 0.15s
```

All 9 fail for the correct reason: the feature is missing (`ImportError`), not a typo.

### GREEN (minimal code)

`src/evaluation/cost_sensitivity.py` adds `cost_envelope_sweep` with the contract above.

```text
.venv/bin/python -m pytest tests/test_cost_envelope.py -v
  9 passed in 2.16s
```

### REFACTOR

No duplication remained: the envelope aggregation is a single pass over the grid cells
and reuses the existing `run_baseline` engine. No behavior change, no new helpers beyond
a small `_cell_drawdown` used only here.

## Raw tests (executed this run)

```text
# New phase-26 suite (GREEN):
.venv/bin/python -m pytest tests/test_cost_envelope.py -v
  9 passed in 2.16s

# Full project regression gate (GREEN, resource guard permitted heavy run):
.venv/bin/python -m pytest tests/ -q
  483 passed in 208.78s   (was 474; +9 new)

# Compileall (whole tree, clean):
.venv/bin/python -m compileall -q src scripts
  -> exit 0 (clean)
```

Per-test results (focused suite):

- test_module_and_function_exist — PASS
- test_rejects_empty_snapshots — PASS
- test_rejects_negative_multiplier — PASS
- test_rejects_nonfinite_multiplier — PASS
- test_envelope_cell_count_and_no_invented_trades — PASS
- test_envelope_worst_cell_is_min_and_best_is_max — PASS
- test_envelope_selection_always_blocked — PASS
- test_envelope_any_profitable_flag_with_fake_engine — PASS
- test_envelope_on_real_history_reports_full_block_and_envelope — PASS

## Mutation check (assertions bind to real logic, not decoration)

Per build-verification, a suite that cannot fail is the same trap as a flat-line metric.
Backed up `src/evaluation/cost_sensitivity.py`, mutated the worst-cell selector
(`worst_cell = min(cells, key=...)` → `max(cells, key=...)`), ran the suite, then
restored from backup.

```text
# under mutation (worst-cell selector inverted):
.venv/bin/python -m pytest tests/test_cost_envelope.py::test_envelope_worst_cell_is_min_and_best_is_max -q
  1 failed
    assert -21.4671005075001 == -24.968408120000028 ± 2.5e-05
    comparison failed (Obtained -21.47 != Expected -24.97)

# restored:
.venv/bin/python -m pytest tests/test_cost_envelope.py -q
  9 passed in 2.22s
  diff against backup: NO DIFF (clean restore)
```

The worst-cell assertion fails under mutation and passes when restored, proving it binds
to the new logic. The other 8 assertions stay green under this mutation because they
exercise non-mutated paths.

## Runtime verification (honest envelope report, local public data only)

`scripts/run_cost_envelope_report.py` runs `cost_envelope_sweep` over already-stored
public `BTCUSDT_1m` history (2500 snapshots) on a 2x2x2 grid (8 cells), no network
egress, and fails closed if `selection_blocked`/`promotion_blocked` is ever `False`.

```text
.venv/bin/python scripts/run_cost_envelope_report.py --symbols BTCUSDT \
  --fee-mults 1.0 2.0 --funding-mults 1.0 2.0 --slippage-mults 1.0 2.0
  symbol: BTCUSDT
  n_snapshots: 2500
  n_cells: 8
  baseline_closed_trades: 44
  baseline_net: -5083.53
  min_net: -8725.41   (worst cell: fee x2, funding x2, slippage x2)
  median_net: -6727.55
  max_net: -4791.79   (best cell:  fee x1, funding x2, slippage x1)
  any_profitable: false
  all_blocked: true
  selection_blocked: true
  promotion_blocked: true
```

The envelope is coherent and honest: even the best grid cell stays negative, so the full
cost sensitivity envelope remains negative. No overclaim of edge.

## Network calls / signed calls / orders / positions

- **Network calls: 0.** No public Bitget acquisition occurred this run. The real-shaped
  test (`test_envelope_on_real_history_reports_full_block_and_envelope`) and the runtime
  report read the already-local `data/history/BTCUSDT_1m.json` (public data acquired by
  an earlier phase), so they exercise real-shaped inputs without any network egress.
- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed). No credentials, demo
  keys, or live keys were used. No signed exchange calls, transfers, withdrawals, or
  funded execution occurred. The change is pure offline evaluation math over in-process
  lists and local files.

## Trades / fees / funding / PnL

No live trades, fees, funding, or realized PnL were produced. This phase is a descriptive
sensitivity envelope over already-measured cost-inclusive baseline returns; it touches no
market simulation or PnL path beyond replaying the existing `run_baseline` engine. The
483 passing tests include the existing cost/funding/slippage stress, walk-forward DSR/Holm,
CSCV, and data-quality suites, which remain green and unmodified by this change.

The runtime report's `baseline_net` (-5083.53) and envelope extremes are
**measurement facts** about the stored public BTCUSDT 1m replay under the documented
assumed half-spread (0.5 bps), not a market verdict and not a go-live claim.

## Protection / reconciliation (unaffected, noted for completeness)

This phase does not alter the protection supervisor or reconciliation engine (strengthened
in earlier phases, most recently the fail-closed wrong-side-stop read-back in phase 23 and
CSCV in phase 24). The envelope is an offline evaluation artifact consumed by the
research/stress path; it has no execution, protection, or reconciliation side effects and
carries `selection_blocked=True` so it cannot influence any live decision.

## Limitations (honest)

- The envelope is a **sensitivity envelope over assumed costs**, not observed
  execution. Spread is the documented assumed half-spread (0.5 bps); historical bid/ask
  is not available from the selected public endpoint. Realistic latency, queue position,
  and partial-fill behavior are not modeled per-cell; the grid scales the assumed
  cost rates, which bounds the *cost* dimension but not microstructure realism.
- The grid is a finite sample of the cost space. A coarser ladder understates the true
  worst case; the defaults (4x3x4 = 48 cells) are a reasonable trade-off and the function
  accepts arbitrary ladders for finer sweeps.
- `median_net` uses `statistics.median` over the cell nets; it is descriptive, not a
  confidence interval, and should be read alongside the per-cell distribution and the
  walk-forward/CSCV robustness metrics.
- The best grid cell being least-negative is an artifact of lower costs, not evidence of
  edge. All cells here are negative; the envelope therefore reinforces the BLOCKED gate.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. This phase strengthens the **realistic cost/funding/slippage
stress** unblocked stream and adds the full sensitivity envelope the review requested; it
adds no selection, LLM, or execution path. Unblocked research/engineering continues per
the cron mandate.

## Commit / publish evidence

- Implementation committed as `5a0f68e` with gh-derived identity
  `𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟 <42990222+hernanda-git@users.noreply.github.com>`.
- Content-level secret scan over the repository (excluding `.git`, `.venv`,
  `__pycache__`): **0 hits**.
- `.env` confirmed git-ignored (`git check-ignore .env` → `.env`).
- Full 483-test suite passed once (~209s) as the verification gate.
- This report (phase-26) is committed in the same push batch.
- Repo remains public (`isPrivate: false`) as required by the standing mandate.
- Note: the already-published history (pre-phase-26 commits) may still contain older
  name variants; per the standing mandate this publication cleanup is separately pending
  and is **not** force-rewritten automatically.
