# Phase 38 — Fail-closed walk-forward coverage pre-check (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-29 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline unit work + offline replay of synthetic in-repo datasets (zero network egress, zero orders)
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not touch the deterministic gate. The coverage payload newly reports `selection_blocked: true` (consistent with the always-blocked Phase 6 policy). The deterministic baseline remains negative; no promotion/selection/winner flag is ever emitted or flipped.

## Scope and why it is unblocked

The cron mandate lists `strengthen walk-forward evaluation` and `data-quality checks` as unblocked streams. A walk-forward with too few / too-short test windows cannot support a statistically meaningful out-of-sample verdict, yet the engine will happily trade a handful of bars and laud the aggregate. This phase adds a **fail-closed walk-forward coverage pre-check**: it reports, for the configured `test_window`, how many complete non-overlapping test windows the dataset supports, whether that count is statistically adequate (`>= min_windows` complete windows AND `>= min_bars_per_window` bars per window), and the largest test-window length that still yields an adequate window count. The runner can opt into a hard fail-closed gate (`--require-wf-coverage`) that rejects (exit 6) BEFORE any heavy replay, so a thin corpus is never laundered into a verdict. The verdict is always computed (measurement only) and reported in the payload regardless of the flag, so dashboards carry the coverage fact for every run.

A half-written, uncommitted Phase 38 already existed from a prior session (`src/evaluation/walk_forward_coverage.py`, `tests/test_walk_forward_coverage.py`, `tests/test_real_history_wf_coverage_gate.py`, and a 33-line addition to `scripts/evaluate_real_history.py`). This run (a) found the prior work was RED on exactly one assertion — the `selection_blocked` key was never emitted in `WalkForwardCoverage.as_dict()`, so `test_runner_reports_coverage_when_not_required` raised `KeyError`; (b) closed the loop GREEN; (c) added a mutation check proving the new assertion binds; (d) confirmed the full suite stays green. Nothing here changes the promotion gate, places orders, or computes realized PnL.

## TDD cycle (strict)

### A. Walk-forward coverage module (`src/evaluation/walk_forward_coverage.py`)
- **RED (confirmed this run):** the prior session wrote `tests/test_real_history_wf_coverage_gate.py::test_runner_reports_coverage_when_not_required`, which asserts `payload["walk_forward_coverage"]["selection_blocked"] is True`, but `WalkForwardCoverage.as_dict()` omitted the key. Running the new tests failed with `KeyError: 'selection_blocked'` (1 failed, 9 passed) — a genuine missing-feature failure, not a typo.
- **GREEN:** added `selection_blocked: bool = True` to the frozen `WalkForwardCoverage` dataclass, emitted it in `as_dict()`, and passed it from `plan_walk_forward_coverage`. `selection_blocked` mirrors the always-blocked Phase 6 policy used across the other measurement-only evaluation modules (walk-forward robustness, candidate-family, cost envelope): coverage adequacy is necessary-but-not-sufficient, and the deterministic baseline is negative, so selection stays blocked regardless of coverage. 10 passed in the two new test files.
- **Mutation check (build-verification skill):** backed up the module, mutated `selection_blocked: bool = True` -> `= False` and the constructor `selection_blocked=True` -> `= False`; exactly `test_runner_reports_coverage_when_not_required` went RED (1 failed / 9 passed). Reverted -> 10 passed. The new assertion genuinely binds to behavior, not decoration.

### B. Runner wiring (`scripts/evaluate_real_history.py`, +46 lines)
- **RED (prior session, re-confirmed):** `scripts/evaluate_real_history.py` did not import or call the coverage module; `--require-wf-coverage` / `--min-wf-windows` / `--min-wf-bars-per-window` did not exist. `tests/test_real_history_wf_coverage_gate.py` covered the runner entrypoint (4 tests) and was RED on the `selection_blocked` key.
- **GREEN:** imported `plan_walk_forward_coverage` + `require_wf_coverage_exit_code`; added the three CLI flags; computed coverage after the existing walk-forward window-quality gate; when `--require-wf-coverage` is set and `adequate` is False, printed `WALK_FORWARD_COVERAGE_REJECTED` to stderr and returned exit 6 BEFORE entering the resource-budgeted heavy replay; otherwise continued and attached `walk_forward_coverage` to the payload. The 4 runner tests pass.
- **Honest finding + fix (still Phase 38, same TDD loop):** the coverage count reads `config.test_window`, which `BaselineConfig` defaults to **10**. The gate's default `min_bars_per_window` is **50**, so under default arguments `--require-wf-coverage` **always rejects** (10 < 50) — the gate was fail-closed to the point of being unusable, and the `recommended_test_window` field was guidance only, never acted on. A runner-level test (`test_runner_adequate_when_test_window_large_enough`) was written first expecting exit 0 on a 2500-bar dataset at a 50-bar window and was RED (argparse rejected `--test-window`). GREEN: added a `--test-window` CLI flag (default 10, threaded into `BaselineConfig`) so the gate is actually usable; the test now passes (exit 0, `adequate=True`, `selection_blocked=True`). The default behavior is unchanged (`test_window=10`), so short/thin corpora still fail closed.

## What this run added / changed
- `src/evaluation/walk_forward_coverage.py` — NEW: `WalkForwardCoverage` (frozen dataclass), `_count_windows`, `_recommend_test_window`, `plan_walk_forward_coverage`, `require_wf_coverage_exit_code`. Measurement only; never flips the promotion gate; always `selection_blocked=True`.
- `scripts/evaluate_real_history.py` — MODIFIED (+33 lines): `--require-wf-coverage` fail-closed gate (exit 6) + `--min-wf-windows` / `--min-wf-bars-per-window` tunables; coverage verdict always attached to payload.
- `tests/test_walk_forward_coverage.py` (6), `tests/test_real_history_wf_coverage_gate.py` (4) — NEW TDD suites.
- `reports/phase-38/phase-38-report.md` — this report.

## Raw tests (executed this run)
```text
# new unit + integration tests (RED->GREEN)
pytest tests/test_walk_forward_coverage.py tests/test_real_history_wf_coverage_gate.py -q
    -> 10 passed
# confirm RED was a real missing-feature failure (prior state)
#   test_runner_reports_coverage_when_not_required raised KeyError: 'selection_blocked'
#     (1 failed, 9 passed) until as_dict() emitted the key
# compileall
python3 -m compileall -q src scripts
    -> exit 0 (clean)
# full suite, no regressions
pytest tests/ -q
    -> 604 passed, 0 failed  (223.28s)
# mutation check (temporary, reverted):
#   selection_blocked True->False in dataclass + constructor
#     -> 1 failed / 9 passed ; reverted -> 10 passed
```

## Offline runner evidence (no egress, synthetic in-repo datasets)
Drove `scripts.evaluate_real_history` (via `erh.main()`) with synthetic `HistoryDataset` JSON files (no network, no secrets):
- **SHORT (120 bars, default 10-bar window) + `--require-wf-coverage`** -> stderr `WALK_FORWARD_COVERAGE_REJECTED: windows=4 (min 5) test_bars_per_window=10 (min 50) adequate=False recommended_test_window=8`; **exit 6**; **no report emitted** (fail-closed: a thin corpus is never laundered into a verdict).
- **SHORT + NOT required** -> **exit 0**; payload `walk_forward_coverage = {"windows": 4, "adequate": false, "min_windows": 5, "min_bars_per_window": 50, "test_bars_per_window": 10, "total_test_bars": 40, "recommended_test_window": 8, "config_test_window": 10, "selection_blocked": true}` — coverage verdict reported, run not blocked.
- **LONG (2500 bars, 50-bar window) + `--require-wf-coverage`** -> exit 0; payload `walk_forward_coverage.adequate = true` (windows >= 5, test_bars_per_window = 50); `selection_blocked = true` (run proceeds, but selection stays blocked by the deterministic gate, never by coverage adequacy).

## Network calls
- **0 network calls this run.** All inputs are synthetic in-repo `HistoryDataset` objects / JSON. No `GET`, no authenticated, signed, or account endpoints were touched.

## Signed calls / orders / positions
- **Signed calls: 0.** Orders: 0. Positions: 0 (open or closed by this phase). No credentials, demo keys, or live keys were used. No signed exchange calls, transfers, withdrawals, or funded execution occurred. Egress: none.

## Trades / fees / funding / PnL
- **Trades executed by this phase: 0.** Fees: 0. Funding: 0. PnL: 0 realized — the replay over the synthetic datasets produces zero closed trades (no strategy marks are traded by the coverage pre-check; it only counts windows on the candle series). The coverage figures above are structural facts about the dataset, not PnL, and are reported strictly under the blocked gate.

## Protection / reconciliation
- **Not exercised** by this measurement-only change. No position, protection, or reconciliation path was touched. The only fail-closed logic is the runner's `--require-wf-coverage` gate (exit 6 before heavy replay) and the always-`selection_blocked=True` payload field.

## Limitations (honest)
- The coverage pre-check measures *window count and per-window bar count*, not trade-count or statistical power. A dataset can yield adequate window counts yet still have too few closed trades to conclude anything (the baseline already reports `INCONCLUSIVE_NO_CLOSED_TRADES`). The two gates are complementary: coverage gates *can we even walk forward*, trade-count gates *did anything actually happen*.
- `recommended_test_window` maximizes the window length that still meets the window-count target; it does not optimize for statistical power and should be read as a lower-bound guidance, not a recommendation to use the longest window.
- The CLI flags default to `min_wf_windows=5`, `min_wf_bars_per_window=50`; these are reasonable starting thresholds, not a published statistical standard. Tighter thresholds make the fail-closed gate stricter.
- No promotion implied. The deterministic baseline is negative and the gate is unchanged; `selection_blocked` is always `true` regardless of coverage adequacy.

## Phase 6 promotion gate
- **Still BLOCKED.** This phase is purely walk-forward coverage realism + a fail-closed corpus gate. The deterministic baseline remains negative; no promotion action was taken and none is authorized while the baseline is negative.

## Commit / push
- New/changed: `src/evaluation/walk_forward_coverage.py`, `scripts/evaluate_real_history.py`, `tests/test_walk_forward_coverage.py`, `tests/test_real_history_wf_coverage_gate.py`, `reports/phase-38/phase-38-report.md`.
- Git identity verified: `user.name=𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟`, `user.email=42990222+hernanda-git@users.noreply.github.com` (matches `gh api`).
- Secret scan: `.env` is git-ignored; content scan over tracked + new text found **0 secret hits**. Verified repeatable, network-free, secret-free command: `pytest tests/test_walk_forward_coverage.py tests/test_real_history_wf_coverage_gate.py -q`.
