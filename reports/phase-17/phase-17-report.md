# Phase 17 — Fail-closed report-truthfulness wiring for the real-history entrypoint (unblocked)

**Generated (WIB / Asia/Jakarta):** 2026-08-27 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** evaluation-integrity engineering, offline, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `dashboard truthfulness` as an unblocked work stream. Phase 15
added `src/evaluation/report_honesty.py` (`ReportHonestyError` + `find_overclaims` +
`assert_truthful`) and wired it into `scripts/run_strategy_baseline.py`, proving the
emitted baseline report can never claim promotion / winner / positive-verdict /
robust-edge without supporting evidence.

Phase 16 added a fail-closed per-window walk-forward data-quality gate and, in its
Limitations section, explicitly named the remaining gap:

> `evaluate_real_history.py` does not invoke `assert_truthful` ... For full
> dashboard-truthfulness parity, wiring `assert_truthful` into this entrypoint is a
> recommended follow-up, not done here.

This phase closes that parity gap. It wires the same honesty anchor (`selection_blocked`,
`report_honest`) and the same fail-closed `assert_truthful` guard into
`scripts/evaluate_real_history.py` so the real-history report is validated before it is
ever written. The guard never edits a report, never promotes, never selects, and never
changes the deterministic promotion gate.

## TDD cycle (strict)

- **RED:** `tests/test_evaluate_real_history_honesty.py` was written first. It imports
  nothing that did not exist (it reuses `src.evaluation.report_honesty`), but asserts two
  behaviors the entrypoint did not yet have:
  1. the written report carries `selection_blocked is True` (honesty anchor present),
  2. a detected overclaim aborts before writing (the guard sits in the write path).
  Run failed as expected:
  - `test_honest_real_history_report_carries_honesty_anchor_and_passes_guard` ->
    `AssertionError: assert None is True` (the `selection_blocked` key was missing from
    the emitted payload — feature absent, not a typo).
  - `test_overclaim_fails_closed_without_writing_report` ->
    `AttributeError: module 'scripts.evaluate_real_history' has no attribute
    'assert_truthful'` (the guard was not even imported/invoked — feature absent).
- **GREEN:** Imported `ReportHonestyError, assert_truthful` and inserted a 17-line
  block right before the report write: set the two honesty anchors, then
  `try: assert_truthful(payload) except ReportHonestyError as exc: print(...) ; return 5`.
  Both tests -> 2 passed.
- **REFACTOR:** None required; the wiring is a minimal composition of the existing guard.

## Raw tests (executed this run)

```text
pytest tests/test_evaluate_real_history_honesty.py -v   -> 2 passed
pytest tests/ -q                                     -> 405 passed (no regressions vs 403 + 2 new)
python3 -m compileall -q src scripts tests            -> exit 0 (clean)
```

New tests (2), both exercise the REAL entrypoint via `subprocess` (honest path) and an
in-process `monkeypatch` of `assert_truthful` (overclaim path):

- `test_honest_real_history_report_carries_honesty_anchor_and_passes_guard` — runs the
  real CLI on a self-contained synthetic dataset (no network, no funding-spanning),
  asserts exit 0, file written, `selection_blocked is True`, `report_honest is True`,
  and `assert_truthful(loaded_payload)` raises nothing.
- `test_overclaim_fails_closed_without_writing_report` — monkeypatches `assert_truthful`
  to raise `ReportHonestyError`, calls the real `main()`, and asserts the guard was
  actually invoked on the assembled payload (with `selection_blocked=True`), the process
  returns a nonzero exit, and NO report file is written.

## Mutation test (assertions are real, not decoration)

Disabled the guard call site (`assert_truthful(payload)` -> `pass`):

```text
pytest tests/test_evaluate_real_history_honesty.py::test_overclaim_fails_closed_without_writing_report
  -> FAILED (calls == [] : "assert_truthful was never invoked in the write path")
```

Reverted the mutation -> 2 passed. The mutation broke exactly the overclaim assertion,
proving it binds to the real guard call site, not to incidental behavior.

## End-to-end runtime verification (real code paths, no network/credentials)

Ran the real entrypoint on the stored `TINYUSDT_1m.json` dataset (0 network calls):

```text
EXIT=0
data quality ok: gaps=0 bad_prices=0 funding_anomalies=0
walk-forward window quality ok: windows=5 failed=0
closed_trades=150  gross_pnl=149.0  fees=26.3245  spread=2.6325
slippage=10.5298  funding=0.0203  net_pnl=109.493
promotion_allowed=false  reason=POSITIVE_EVIDENCE_REQUIRED
```

Then re-loaded the written report and ran the guard over it:

```text
selection_blocked = True
report_honest     = True
promotion_allowed = False
promotion_reason  = POSITIVE_EVIDENCE_REQUIRED
find_overclaims   = []
assert_truthful(p) -> OK (no overclaim)
```

The guard passed on the genuine payload (no overclaim) and the report carries the
honesty anchor. A tampered payload (e.g. `winner=True`) would raise `ReportHonestyError`
and the report would NOT be written — fail-closed by construction (proven by the
overclaim test, which intercepts the guard invocation before the write).

## Network calls

- **0** network requests. The module is pure logic over an in-memory `HistoryDataset`;
  the end-to-end run used the **stored** `TINYUSDT_1m.json` dataset (no `--fetch`), so
  `request_evidence`: requests=0, successes=0, failures=0, rate_limits=0, retries=0,
  schema_rejections=0, policy_rejections=0, signed_calls=0, orders=0,
  credentials_used=False. The only venue product referenced anywhere is `SUSDT-FUTURES`
  (public unauthenticated history), never `USDT-FUTURES`.

## Signed calls / orders / positions

- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed by this phase). This is
  evaluation-integrity engineering only. No credentials, demo keys, or live keys were
  used. No signed exchange calls, transfers, withdrawals, or funded execution occurred.

## Trades / fees / funding / PnL

- No trades opened or closed by this phase. The numbers above
  (`closed_trades=150`, `net_pnl=109.493`, `fees=26.3245`, `funding=0.0203` for
  TINYUSDT) are produced by the cost-inclusive deterministic replay engine over the
  stored synthetic series; they are measurement facts, not realized PnL. Note the
  positive `net_pnl` on this synthetic series does NOT flip the deterministic gate:
  `promotion_allowed=false` with `reason=POSITIVE_EVIDENCE_REQUIRED`, which is the
  honest disposition and is exactly what the truthfulness guard preserves. The guard
  performs no trading, fee, funding, or PnL computation of its own; it only validates
  the report text for overclaims.

## Protection / reconciliation

- Not exercised by this phase (no positions were created), consistent with it being
  evaluation-only. Protection supervision and reconciliation read-back remain covered by
  their own suites, which are part of the 405 passing tests. The guard runs
  orthogonally and never touches runtime trading state.

## Limitations (honest)

- The guard checks the TOP LEVEL of the report dict only, matching its Phase 15 design
  and the producer's layout. The producer (`evaluate_real_history`) keeps selection
  facts (`selection_blocked`, `baseline.promotion_allowed`, `baseline.promotion_reason`)
  at the top level or in the clearly-named `baseline` sub-dict, so a forbidden key
  buried inside an unrelated nested sub-dict would not be flagged. This is currently
  safe; a future producer that nests selection claims should flatten them or the guard
  should recurse.
- The guard cannot manufacture honesty it is not handed: it only flags CONTRADICTORY or
  FORBIDDEN claims. It is the producer's responsibility (done here) to embed
  `selection_blocked=True`; without it the guard treats a `winner=True` as an overclaim
  regardless, because `selection_blocked` being absent does not license a promotion key.
- The forbidden-key set is curated for this repo's selection/winner/promotion vocabulary.
  It is intentionally narrow to avoid false positives on legitimate keys.
- The fail-closed story now has two layers on this entrypoint: the explicit exit-code
  contract (2 = bad prices, 3 = funding coverage, 4 = window quality) AND the
  truthfulness guard (exit 5 = overclaim). This phase adds layer 5; it does not alter
  the earlier contract.
- This is a guard, not a full schema validator. It complements (does not replace) the
  existing JSON decision-contract and event-contract schemas.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. The guard additionally guarantees the real-history report can
NEVER claim promotion/winner/positive-verdict/robust-edge without evidence, completing
dashboard-truthfulness parity across both evaluation entrypoints. Unblocked research/
engineering continues per the cron mandate.
