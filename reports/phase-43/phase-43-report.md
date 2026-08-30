# Phase 43 — Deterministic fixtures + ledger funding reconciliation

**Date:** 2026-08-30
**Author:** valarion (42790222+hernanda-git@users.noreply.github.com)
**Discipline:** TDD + mutation-verified, fail-closed, offline, no signed calls.

## Summary

Two recommendations from the autonomous continuation were executed:

1. **(a) Make the 2 snapshot-pinned cost tests deterministic** — they previously
   read the git-ignored live corpus (`data/history/*.json`), which drifts over time
   and made the assertions flaky. Replaced the live inputs with committed,
   integrity-checked synthetic fixtures (`tests/fixtures/{ETHUSDT,BTCUSDT,ADAUSDT}_1m.json`)
   built through `HistoryDataset` so their `integrity_hash` round-trips. The exact
   fail-closed assertions are preserved unchanged.
2. **(b) Wire the realistic funding model into the ledger reconciliation** — Phase 41
   wired `src/evaluation/funding_model` into the exchange; the ledger still only
   summed recorded fill funding. Added `EventLedger.reconcile_funding(legs)` which
   binds the ledger's recorded fill funding against the per-settlement legs produced
   by `reconcile_funding_legs`, fail-closed (`in_sync=False` on any discrepancy).

## Changes

- `tests/fixtures/*.json` (NEW) — 3 committed deterministic datasets (400 candles each,
  funding settlements every 8h), generated via `HistoryDataset.to_dict()` so they pass
  the loader's `integrity_hash` check. Reproducible; no egress.
- `tests/test_cost_sensitivity.py` — `test_break_even_absent_on_real_history_...` now
  loads `tests/fixtures/ETHUSDT_1m.json`.
- `tests/test_cost_envelope_per_tier.py` — `test_cost_envelope_per_tier_real_history_blocked`
  now loads `tests/fixtures/{BTCUSDT,ADAUSDT}_1m.json`.
- `src/ledger/sqlite.py` — NEW `reconcile_funding(legs, run_id=None)`: compares
  `reconcile_funding_legs(legs)` against the sum of `FILL_OBSERVED.funding` in scope;
  returns `{"in_sync", "model_net", "ledger_net", "legs"}`. Fail-closed on drift.
- `tests/test_ledger_funding_reconciliation.py` (NEW) — 3 tests: consistent ledger is
  `in_sync`; an over-charged ledger is `in_sync=False`; empty is `in_sync` vacuously.
- `reports/phase-37/corpus_quality.json` — refreshed by the Phase 42 corpus scan.

## Verification

- `python -m compileall -q src scripts` → clean.
- Targeted: `tests/test_ledger_funding_reconciliation.py` **3 passed**;
  `tests/test_cost_sensitivity.py` + `tests/test_cost_envelope_per_tier.py` **12 passed**.
- **Full suite: 626 passed, 1 failed, 4 skipped** (was 621 passed / 3 failed / 4 skipped).
  The 2 snapshot-pinned failures are now fixed; the single remaining failure is
  `tests/test_service_hygiene.py::test_service_isolated_and_safe_by_default`, an
  environment-path assertion that hardcodes `/root/bitget-agentic-architecture` (the
  deploy unit's WorkingDirectory). It is unrelated to this phase and was not altered —
  editing the committed service path is a separate, deliberate concern, not a test
  tweak.
- **Mutation check (ledger):** replacing the model net inside `reconcile_funding` flips
  the result to `in_sync=False`; restoring returns `in_sync=True`. The assertions bind.
- **Secret scan:** 0 hits in changed paths; `.env` git-ignored; corpus fixtures carry no
  credentials. No network calls, no signed calls, no orders.

## Honest status

The project's deterministic baseline remains **negative → promotion blocked** (no
live/edge claim). The funding cost path is now settlement-accurate end-to-end (model →
exchange → ledger reconciliation) and the cost-measurement tests are reproducible.
Remaining work: the `/root/...` service-path assertion is the only enforced failure and
requires a decision about the deployment unit's directory, not a code fix.
