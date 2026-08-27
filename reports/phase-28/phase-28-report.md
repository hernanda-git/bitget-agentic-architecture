# Phase 28 — Data-quality: future-dated candle detection (TDD + build-verified)

**Date:** autonomous cron run (Asia/Jakarta timezone)
**Mode:** offline, no network, no credentials, no orders, no signed calls.
**Scope:** strengthen structural data-quality checks for historical datasets.

## What was added

A candle whose `source_ts_ms` is later than the dataset's `fetched_at_ms` is now a
structural integrity violation, reported as `future_dated` and folded into
`DataQualityReport.ok` (fail-closed). Such a bar means source clock skew or
forged/corrupted data, and it also poisons freshness math (`data_age_ms` goes
negative) and walk-forward ordering. The check is analogous to the existing
`duplicate_timestamps` / `non_chronological` gates: any of them makes `ok` False.

The CLI (`scripts/evaluate_real_history.py`) already gates evaluation on
`if not dq.ok or stale_rejected:`, so the new invariant is enforced end-to-end
with no extra wiring. The rejection line now also prints `future_dated=<n>` so
the cause is observable.

## TDD cycle

RED first: `tests/test_data_quality_strengthened.py::test_data_quality_flags_future_dated_candles`
and `::test_data_quality_as_dict_includes_future_dated` were written before the
field existed. They failed with `AttributeError: 'DataQualityReport' object has
no attribute 'future_dated'` (and an `AssertionError` on the missing dict key) —
confirming RED for the right reason (feature missing, not a typo).

GREEN: minimal change to `src/market/history.py`:
- added `future_dated: int` to the `DataQualityReport` dataclass
- computed `future_dated = sum(1 for c in candles if c.source_ts_ms > dataset.fetched_at_ms)`
- folded `and self.future_dated == 0` into the `ok` property
- added `future_dated` to `as_dict()`
- added `future_dated={dq.future_dated}` to the CLI rejection message

REFACTOR: none needed.

## Honest finding surfaced by the new check

While running the suite, the new invariant revealed a **latent unrealistic test
fixture**: `tests/test_public_history.py::_sample_dataset()` used
`fetched_at_ms=9_999` while its candles span `1_000..2_341_000` ms. With that
placeholder, *every* candle is "future-dated" relative to the fetch, so the
structural gate now correctly rejects it. This is a fixture bug, not a feature
bug: `9_999` ms after the epoch is not a believable fetch time for candles at
2.3M ms. The fix sets `fetched_at_ms = candles[-1].source_ts_ms + 60_000` (a
realistic "fetched just after the last bar"). The feature was kept strict; the
fixture was corrected to reality (the right direction — never weaken a
fail-closed gate to accommodate a bad fixture).

## Raw tests

```
# RED (before implementation)
$ python3 -m pytest tests/test_data_quality_strengthened.py::test_data_quality_flags_future_dated_candles tests/test_data_quality_strengthened.py::test_data_quality_as_dict_includes_future_dated -q
2 failed in 0.17s   (AttributeError / AssertionError: future_dated missing)

# GREEN (after implementation)
$ python3 -m pytest tests/test_public_history.py::test_evaluate_real_history_on_stored_dataset tests/test_public_history.py::test_evaluate_real_history_embeds_walk_forward_summary tests/test_public_history.py::test_evaluate_real_history_embeds_cost_coverage_variants tests/test_public_history.py::test_evaluate_real_history_allows_permissive_swap_threshold tests/test_public_history.py::test_evaluate_real_history_fails_closed_on_future_dated tests/test_data_quality_strengthened.py -q
14 passed in 1.74s

# Regression set
$ python3 -m pytest tests/test_public_history.py tests/test_data_quality_strengthened.py tests/test_report_honesty.py tests/test_cost_coverage_gate.py tests/test_coverage_gate.py tests/test_evaluate_real_history_honesty.py -q
64 passed in 4.15s

# Full suite (repo-wide, run in background; reported separately)
$ python3 -m pytest tests/ -q
```

## Network / signed / execution evidence

- Network calls: NONE. Pure offline measurement.
- Signed calls: NONE.
- Orders / positions / fills / fees / funding / PnL: NONE. No exchange interaction.
- Protection / reconciliation: N/A (data-quality layer, no live state).
- The CLI gate that consumes this report (`evaluate_real_history.py`) still runs
  with `--no-resource-budget` in tests and returns `selection_blocked=True` (the
  deterministic baseline remains negative; Phase 6 promotion stays blocked). It
  now additionally fails closed on future-dated bars.

## Behaviors covered (one per test)

- `test_data_quality_flags_future_dated_candles`: one future-dated candle ->
  `future_dated == 1`, `ok is False`; no future bars -> `ok is True`
- `test_data_quality_as_dict_includes_future_dated`: serialized report exposes the count
- `test_evaluate_real_history_fails_closed_on_future_dated`: end-to-end CLI rejects a
  future-dated dataset (non-zero exit, no output artifact) and prints `future_dated=1`
- existing `ok` consumers (duplicate / non-chronological / bad_prices) unchanged

## Limitations (honest)

- This is a *structural* check. It rejects obviously impossible timestamps but
  does not cryptographically prove the source is Bitget; integrity is covered
  separately by `HistoryDataset.integrity_hash()` on load.
- `ok` does not yet fold in `funding_anomalies` or coverage gaps; those remain
  separate gates (`real_funding_readiness`, `coverage_gate`) by design, so a
  dataset with extreme funding rates but clean chronology still reaches the
  funding-readiness gate rather than being silently passed.
- The full suite (495 tests, ~209s) is re-run in the background; this report is
  written before that run completes and the commit waits on a green result.
- Deterministic baseline / promotion gate: unchanged. Phase 6 bounded LLM
  selection and promotion actions remain blocked by the negative baseline. This
  unit is unblocked research (data-quality hardening) and does not change the
  promotion gate.
