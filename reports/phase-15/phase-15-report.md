# Phase 15 — Evaluation report truthfulness guard (dashboard truthfulness), fail-closed (unblocked)

**Generated (WIB / Asia/Jakarta):** 2026-08-27 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** evaluation-honesty engineering, offline, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `dashboard truthfulness` as an unblocked work stream. The
`build-verification` skill documents a concrete failure mode for this exact repo:
a hand-maintained status ledger (`⬜/✅` checkpoint file) can OVERCLAIM — a `✅`
there is only a claim the agent wrote, not evidence the artifact exists. A
summary/dashboard can do the same: stamp `promoted: true`, a `verdict: PASS`,
`robust_edge: true` without supporting evidence, or `profitable: true` while net
PnL is negative. Those claims would launder a `NEGATIVE_NET_PNL` blocked baseline
into something that looks go-live ready.

This phase adds a fail-closed guard, `src/evaluation/report_honesty.py`
(`ReportHonestyError` + `find_overclaims` + `assert_truthful`), and wires
`assert_truthful` into `scripts/run_strategy_baseline.main` so the real baseline
report is validated before it is ever written. The guard never edits a report,
never promotes, never selects, and never changes the deterministic gate.

## TDD cycle (strict)

- **RED:** `tests/test_report_honesty.py` was written first, importing
  `src.evaluation.report_honesty` (did not exist). Run failed:
  `ModuleNotFoundError: No module named 'src.evaluation.report_honesty'`.
- **GREEN:** Implemented the module (pure, fail-closed). `tests/test_report_honesty.py`
  -> 17 passed.
- No refactor needed; the module is a small pure function.

## Raw tests (executed this run)

```text
pytest tests/test_report_honesty.py -v            -> 17 passed
pytest tests/ -q                                  -> 397 passed  (no regressions vs 380 + 17 new)
python3 -m compileall -q src scripts tests        -> exit 0 (clean)
```

Coverage (17 tests):
- Forbidden promotion/selection keys (`promoted`, `selected`, `winner`,
  `edge_confirmed`, `go_live_ready`, `phase6_promoted`, `promoted_candidate`)
  raise; multiple keys all reported; a falsy key is NOT an overclaim.
- Forbidden verdict strings (`PASS`/`POSITIVE`/`APPROVED`/`GO_LIVE`/`WINNER`,
  case-insensitive) raise.
- `robust_edge=True` WITHOUT `dsr_positive` + `adequate_sample` + `holm_surviving>=1`
  raises; WITH full evidence it is allowed; missing `holm_surviving` raises.
- `profitable`/`positive_expectancy`=True contradicting net PnL <= 0 raises;
  allowed when net PnL > 0; non-numeric net PnL raises (cannot assert profit).
- Explicit `promotion_gate`=POSITIVE while `selection_blocked`=True raises.
- Empty report and a fully honest `selection_blocked` report pass; non-dict input
  raises `TypeError`.
- Integration: the REAL assembled baseline payload (`run_baseline` + `run_walk_forward`
  + `run_cost_stress` + `run_stress_matrix` + `compute_statistics`) passes the guard;
  the same payload tampered with `winner=True` is rejected.

## Mutation test (assertions are real, not decoration)

Disabled the forbidden-promotion-key guard (`if key in report and _truthy(...)` ->
`if False:`, backup restored afterward):

```text
pytest tests/test_report_honesty.py -q
  FAILED test_forbidden_promotion_key_raises
  FAILED test_multiple_forbidden_keys_all_reported
  FAILED test_tampered_baseline_payload_is_rejected
  3 failed, 14 passed    <- exactly the forbidden-key assertions went red
```

Restored the file -> 17 passed. The mutation broke ONLY the three tests that assert
the forbidden-key behavior, proving the assertions bind to the real guard.

## End-to-end runtime verification (real code paths, no network/credentials)

Wired `assert_truthful(payload)` into `scripts/run_strategy_baseline.main` (with a
fail-closed honesty anchor `selection_blocked=True`, `report_honest=True` added to
the payload). Ran the real script:

```text
.venv/bin/python scripts/run_strategy_baseline.py --output /tmp/baseline_check.json
EXIT=0
payload now carries: "selection_blocked": true, "report_honest": true
and the honest facts already present:
  "promotion_allowed": false, "promotion_reason": "NEGATIVE_NET_PNL",
  "net_pnl": -22.63420203000006, "closed_trades": 15,
  "statistics": {"status": "NOT_EVIDENCED", "reason": "MINIMUM_SAMPLE_NOT_MET"}
```

The guard passed on the genuine payload (no overclaim) and the report was written.
A tampered payload (`winner=True`) would raise `ReportHonestyError` and the report
would NOT be written — fail-closed by construction.

## Network calls

- **0** network requests. The module is pure logic over an in-memory dict; the
  integration run used stored synthetic series only. `request_evidence`:
  requests=0, successes=0, failures=0, rate_limits=0, retries=0, schema_rejections=0,
  policy_rejections=0, signed_calls=0, orders=0, credentials_used=False.

## Signed calls / orders / positions

- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed by this phase). This
  is evaluation-honesty engineering only. No credentials, demo keys, or live keys were
  used. The only venue product referenced anywhere is `SUSDT-FUTURES` (public
  unauthenticated history), never `USDT-FUTURES`.

## Trades / fees / funding / PnL

- No trades opened or closed by this phase. The numbers above (`closed_trades=15`,
  `net_pnl=-22.63`, `fees`, `funding`) are produced by the cost-inclusive
  deterministic replay engine over the synthetic baseline series; they are
  measurement facts, not realized PnL, and remain negative. `report_honesty` performs
  no trading, fee, funding, or PnL computation of its own; it only checks the report
  text for overclaims.

## Protection / reconciliation

- Not exercised by this phase (no positions were created), consistent with it being
  evaluation-only. Protection supervision and reconciliation read-back remain covered
  by their own suites, which are part of the 397 passing tests. The guard runs
  orthogonally and never touches runtime trading state.

## Limitations (honest)

- The guard checks the TOP LEVEL of the report dict only. A forbidden key buried
  inside a nested sub-dict (e.g. `walk_forward_evaluation[0]["winner"]`) would not be
  flagged. The producer (`run_strategy_baseline`) keeps selection facts at the top
  level, so this is currently safe; a future producer that nests selection claims
  should flatten them or the guard should recurse.
- The guard cannot manufacture honesty it is not handed: it only flags CONTRADICTORY
  or FORBIDDEN claims. A report that simply omits `selection_blocked` and omits any
  forbidden key is judged honest by this guard (an empty `{}` passes). The producer is
  responsible for embedding `selection_blocked=True`; this phase does that for
  `run_strategy_baseline`.
- The forbidden-key set is curated for this repo. A new legitimate key that happens to
  coincide with a forbidden name would be a false positive; the set is intentionally
  narrow (selection/winner/promotion vocabulary) to avoid that.
- This is a guard, not a full schema validator. It complements (does not replace) the
  existing JSON decision-contract and event-contract schemas.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. The guard additionally guarantees the emitted report can
NEVER claim promotion/winner/positive-verdict/robust-edge without evidence, closing
the dashboard-truthfulness gap. Unblocked research/engineering continues per the cron
mandate.
