# Phase 22 — Fail-closed flat-line (dead-metric) detector for report truthfulness (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-28 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline test-integrity engineering (measurement only), no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `dashboard truthfulness` and `report honesty` as unblocked streams. The
build-verification skill (and the Phase 21 report) surface a concrete failure mode: a derived
metric that never varies is WORSE than no metric, because it launders silence as a result
(e.g. the `observer` instance that logged `conviction=0.0 / converged_axis=none` across 17
snapshots while the service reported "active"). The existing report-honesty guard
(`assert_truthful`) catches overclaims about verdicts and selection, but it does NOT catch a
numeric series embedded in a report/dashboard payload that is entirely constant over a window
and is therefore a dead, non-signalling metric.

This phase adds a second, independent layer to the report-honesty guard:
`assert_no_suspect_constant_series` (and its pure predicate `find_suspect_constant_series`),
which fails closed (raises `ReportHonestyError`) if any numeric series in a report is constant
over >= `min_samples` (default 3) samples. It is wired into the honest baseline entrypoint
(`scripts/run_strategy_baseline.py`) so the emitted payload cannot carry a dead metric.

This is strictly measurement/honesty engineering. It does not touch trading state, policy,
protection, or the selection gate. Phase 6 remains blocked.

## Resource guard (run at start of every run)

```text
python3 scripts/resource_guard.py --json
  ok: true
  violations: []
  swap_used_percent: 85.59 (< policy max 90.0)
  available_memory_bytes: 1671254016
  disk_free_bytes: 31748358144
  inode_free_percent: 50.16
```

The guard is GREEN, so the full heavy suite (which the swap-pressure block deferred in Phase 21)
was permitted and run this run as the regression gate.

## TDD cycle (strict)

The feature arrived in the working tree as a complete, untracked-cycle continuation from a prior
run (test file `tests/test_report_flatline.py` present and untracked; implementation present in
`src/evaluation/report_honesty.py`; wiring present in `scripts/run_strategy_baseline.py`). This
run verifies the cycle end-to-end rather than re-implementing it:

### GREEN — verify the feature passes

```text
.venv/bin/python -m pytest tests/test_report_flatline.py -v
  12 passed in 0.13s
```

The 12 tests cover: constant zero / nonzero / integer series flagged; varied series ignored;
short series (< min_samples) ignored; non-numeric lists ignored; recursion into nested dicts and
lists-of-dicts; custom `min_samples`; the `assert_*` wrapper raising on a flat-line and allowing
varied; and a guard that the genuine, un-tampered baseline payload does NOT carry a dead metric
(`test_assert_no_suspect_constant_series_allows_honest_baseline_payload`).

### RED — mutation check (assertions are real, not decoration)

Per the build-verification skill, a suite that cannot fail is the same trap as a flat-line
metric. The flat-line assertions were mutation-tested manually (backup -> mutate -> run -> restore):

- Mutation: disable detection by forcing the series-match condition `and False`.
- Expected: the assertions that *require* detection should go RED; the "ignores" assertions
  (which expect NO flag) should remain GREEN because a disabled detector also emits no false flag.

```text
.venv/bin/python -m pytest tests/test_report_flatline.py -q   # under mutation
  7 failed, 5 passed in 0.16s
  FAILED: flags_constant_zero_series, flags_constant_nonzero_series,
          flags_constant_integer_series, recurses_into_nested_dicts,
          recurses_into_lists_of_dicts, respects_custom_min_samples,
          assert_no_suspect_constant_series_raises_on_flatline
  5 passed (the "ignores varied/short/non-numeric" + baseline-allows-varied)
```

The exact detection-binding assertions fail, proving they bind to the real detection logic and
are not decoration. The file was restored from backup and re-verified GREEN (12 passed).

### REFACTOR — none required

The addition is a self-contained recursive scanner (bounded by `MAX_SCAN_DEPTH`) with no
duplication of the existing overclaim logic.

## Raw tests (executed this run)

```text
# New flat-line layer (GREEN):
.venv/bin/python -m pytest tests/test_report_flatline.py -v
  12 passed in 0.13s

# Full project regression gate (permitted because resource guard is GREEN):
.venv/bin/python -m pytest tests/ -q
  440 passed in 201.76s

# Compileall (whole tree, clean):
.venv/bin/python -m compileall -q src scripts tests
  -> exit 0 (clean)

# Mutation check (manual, not committed): 7 failed / 5 passed under mutation,
# restored to 12 passed. See RED above.
```

## Network calls / signed calls / orders / positions

- **Network calls: 0.** All tests use synthetic fixtures or httpx `MockTransport`. No public
  Bitget acquisition occurred this run.
- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed). No credentials, demo keys, or
  live keys were used. No signed exchange calls, transfers, withdrawals, or funded execution
  occurred. The detector runs purely over in-process report/dict structures.

## Trades / fees / funding / PnL (measurement facts, synthetic fixture, not realized PnL)

No trades, fees, funding, or realized PnL were produced. The only data touched is the synthetic
baseline payload used by `test_assert_no_suspect_constant_series_allows_honest_baseline_payload`,
which asserts the genuine payload carries no constant series. This is a correctness check on the
report structure, not a market verdict.

## Protection / reconciliation

Not exercised by this phase (no positions created or read back). The flat-line detector is a
report-level honesty guard that runs after evaluation and before emission; it cannot affect
runtime trading state, protection, or reconciliation, which remain covered by their own suites
(part of the 440 passing tests). Fail-closed behavior is preserved: a constant series in the
payload now raises and blocks emission.

## Limitations (honest)

- This detector flags any numeric series that is *entirely constant* over >= `min_samples`
  samples. A legitimately constant value (e.g. a window that genuinely had zero trades in every
  bucket, encoded as `[0,0,0,0]`) would be flagged. This is intentional and fail-closed: a dead
  constant is treated as a suspect metric rather than silently emitted. Authors must either
  remove the dead series or demonstrate it is not presented as a live signal. The honest
  baseline payload test proves the project's own payload does not trip this.
- The detector does not catch a *near*-constant series (variance within epsilon) or a series
  constant only after a warmup; those are out of scope for this layer and explicitly left for
  future work to avoid false positives.
- The mutation check was performed manually (backup/mutate/restore) and is reported here rather
  than committed as a permanent test, matching the build-verification skill's prescribed
  procedure.
- The full 440-test suite was run once and passed; it is the project's verification gate and is
  heavy (~202s CPU).

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. This phase strengthens report/dashboard truthfulness (an unblocked
stream) and adds no selection, LLM, or execution path. Unblocked research/engineering continues
per the cron mandate.
