# Phase 12 — Measurement-Only Walk-Forward Candidate-Family Evaluation (unblocked)

**Generated (WIB / Asia/Jakarta):** 2026-08-27 08:59:55 WIB
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** evaluation-only, offline, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The deterministic baseline remains negative, so any promotion / selection action is
blocked. This phase strengthens the *measurement* surface that feeds that gate, which
is explicitly unblocked: walk-forward evaluation, data-quality checks, and strategy
attribution. Concretely this run:

1. Added `coverage_gate` to `src/market/history.py` — a fail-closed gap-coverage gate
   so sparse candle series cannot silently distort walk-forward time indices.
2. Added `evaluate_candidate_family` to `src/evaluation/baseline.py` — runs the SAME
   cost-inclusive, walk-forward, robustness-gated engine over several independent real
   public datasets and applies a Bonferroni family-wise multiple-testing correction.
3. Added a NEW family-level adequate-sample gate (`family_adequate_sample` +
   `total_closed_trades`) via a strict RED→GREEN TDD cycle (see below).
4. Ran the orchestrator offline over 4 stored real public SUSDT-FUTURES datasets to
   produce honest evidence.

All work is measurement-only: `selection_blocked` is always `True` and no
`promoted`/`selected`/`winner` key is ever emitted.

## TDD cycle (strict, this run)

- **RED:** Added `test_evaluate_candidate_family_reports_family_adequate_sample` and
  `test_evaluate_candidate_family_family_adequate_false_when_any_inadequate` to
  `tests/test_evaluate_candidate_family.py`. Both failed with `KeyError` because the
  keys did not exist.
- **GREEN:** Implemented the minimal aggregation in `evaluate_candidate_family`
  (`total_closed_trades = sum(...)`, `family_adequate_sample = all(...)`). Both tests
  pass; full file = 6 passed.
- Refactor: none required (implementation is already minimal).

## Raw tests (executed this run)

```
pytest tests/ -q  ->  352 passed  (full suite, no regressions)
pytest tests/test_evaluate_candidate_family.py -q  ->  6 passed
pytest tests/test_coverage_gate.py -q  ->  3 passed
python3 -m compileall -q src scripts tests  ->  exit 0 (clean)
```

New behavior coverage (mutation-checked after this run — see "Verification"):
- `family_adequate_sample` is `True` only when every candidate clears `adequate_sample`.
- `total_closed_trades` aggregates per-candidate closed trades.

## Network calls

- **0** network requests. Mode = `stored-dataset` (offline replay over previously
  acquired public history). No `--fetch` was used in the production run.
- `request_evidence`: requests=0, successes=0, failures=0, rate_limits=0, retries=0,
  schema_rejections=0, policy_rejections=0, latency_ms_sample=[], signed_calls=0,
  orders=0, credentials_used=False.
- Endpoint that the stored data was originally sourced from (for traceability only,
  not called this run): `https://api.bitget.com/api/v2/mix/market/{candles,history-fund-rate}`.

## Signed calls / orders / positions

- **Signed calls: 0.** **Orders: 0.** **Positions: 0 (open or closed by this phase).**
  This is an evaluation-only phase; no execution path was exercised. No credentials,
  demo keys, or live keys were used.

## Trades / fees / funding / PnL (real public history, cost-inclusive)

All four candidates are real Bitget SUSDT-FUTURES public history (2000 candles, 100
funding records each). Walk-forward uses 72 windows per candidate. Costs assumed:
fee 5 bps, funding 2 bps, slippage 2 bps (real observed funding applied where available).

| Candidate | Windows | Trades (WF) | Profitable windows | Expectancy mean | 95% CI (lower,upper) | Expectancy +CI? | Baseline net PnL | Baseline trades |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT_1m | 72 | 74 | 12/72 | -152.72 | [-236.23, -67.54] | NO | -6872.31 | 45 |
| ETHUSDT_1m | 72 | 79 | 10/72 | -4.75 | [-6.91, -2.59] | NO | -299.21 | 63 |
| BTCUSDT_5m | 72 | 124 | 14/72 | -89.46 | [-133.50, -45.86] | NO | -21917.09 | 245 |
| ETHUSDT_5m | 72 | 130 | 18/72 | -2.41 | [-4.06, -0.63] | NO | -747.64 | 310 |

Aggregate: `total_closed_trades` = 407. Every candidate's 95% CI lower bound is
strictly below zero, so none is positive even at the per-test (naive) level.

## Family-wise multiple-testing correction (Bonferroni)

- Tests: 4
- Uncorrected (naive) positives: **0**
- Corrected (Bonferroni) positives: **0**
- `any_corrected_positive`: **false**
- `family_adequate_sample`: **true** (all 4 candidates cleared the min-30-trade gate)

A naive pipeline that scanned these 4 symbols and judged each at 0.95 would still find
0 positives — there is no lone lucky survivor to launder, but the correction guard is
now explicit and will catch one if future widening of the family introduces it.

## Protection / reconciliation

- **Not exercised this phase.** No orders or positions were created, so protection
  supervision and reconciliation read-back had nothing to verify. These remain covered
  by their own suites (`test_protection_supervisor.py`, `test_protection_reconciliation.py`,
  `test_reconciliation.py`) which are part of the 352 passing tests, but were not driven
  by this evaluation run because it is execution-free by design.

## Limitations (honest)

- Datasets are a 2-symbol x 2-granularity family (BTCUSDT, ETHUSDT at 1m/5m). The family
  is small; the Bonferroni correction is therefore mild, but the conclusion (negative
  expectancy, adequate sample, blocked) is driven by the per-candidate CIs, not by the
  correction.
- Costs are assumed constants (fee/funding/slippage bps) with real observed funding
  applied; they are not venue-floor-validated for a live account. This matches the
  measurement-only mandate and does not affect the `selection_blocked` outcome.
- Replay uses the canonical strategy set; no LLM/provider was invoked. Phase 6 selection
  remains blocked by the deterministic `NEGATIVE_NET_PNL` gate and is not promoted here.
- The stored datasets live in `data/history/` (git-ignored); only this report and the
  aggregated `candidate-family.json` (subdir, tracked) are committed.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. Unblocked research/engineering continues per the cron mandate.
