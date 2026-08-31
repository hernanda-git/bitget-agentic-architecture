# Phase 49 — Fail-closed corpus-staleness observation (TDD + mutation-verified)

**Date:** 2026-08-31
**Author:** valarion (42990222+hernanda-git@users.noreply.github.com)
**Discipline:** TDD + mutation-verified, fail-closed, offline, no signed/order calls.
**Bounded phase source:** directive §7 ("watch corpus staleness") — the explicit
"Next candidate" deferred by the Phase 48 report.

## Summary

The heartbeat had no code to answer "is the blessed public-history corpus still fresh?".
This phase lands `src/evaluation/corpus_staleness.py`: a read-only observation that derives
freshness from each dataset's honest `fetched_at_ms` acquisition timestamp (written by
`scripts/acquire_corpus.py`) — never from the wall clock at read time, and never from the
file mtime, both of which could launder a stale corpus into "fresh".

Fail-closed by construction. The corpus is reported `stale=True, reason="no_fresh_corpus",
present=False` whenever no readable dataset carries a usable acquisition timestamp:

- corpus directory missing or empty,
- every dataset file corrupt/unreadable (`JSONDecodeError`/`OSError` → skipped, never trusted),
- only `corpus_manifest.json` present (a manifest is not evidence of a fresh dataset).

Default threshold `DEFAULT_MAX_AGE_MS` = 7 days. `main()` exits `0` when fresh and `75` when
stale, so a scheduler can gate heavy work on corpus freshness without a bespoke parser.

### Integrity finding recovered this tick

A previous tick died **mid-mutation-verification** and left its mutation stranded in the
working tree, uncommitted:

```python
stale = False  # MUTATION: guard disabled to prove binding
```

The staleness guard was therefore live-disabled on disk. This tick caught it, used it as
genuine RED evidence, restored the real guard, and re-verified. Nothing was committed while
the mutation was in place. Lesson recorded in Pitfalls: an interrupted mutation check leaves
a disabled guard behind — always re-read the mutated line before committing.

## Changes

- Create `src/evaluation/corpus_staleness.py` — `CorpusFreshness` dataclass (frozen,
  `as_dict()`), `evaluate_corpus_freshness()`, `DEFAULT_MAX_AGE_MS`, `main()` CLI.
- Create `tests/test_corpus_staleness.py` (7 tests).
- Restore the stranded mutation: `stale = fresh_ms > max_age_ms`.

No trading/research logic touched. No promotion claim.

## Verification

- `python -m compileall -q src scripts` → clean (`COMPILE_OK`).
- `tests/test_corpus_staleness.py` → **7 passed**.
- **RED proven first:** with the stranded mutation in place,
  `test_stale_dataset_reports_stale` failed on
  `assert result.stale is True` → `AssertionError: assert False is True`
  (`CorpusFreshness(..., stale=False, reason='fresh', fresh_ms=604800001)`) — a real
  behavioural failure, not a typo.
- **Mutation check 1 (age guard):** `stale = fresh_ms > max_age_ms` → `stale = False`
  flips `test_stale_dataset_reports_stale` RED. Reverted.
- **Mutation check 2 (fail-closed branch, isolated):** in the `if not fetched:` return,
  `stale=True` → `stale=False` flips **3** tests RED
  (`test_missing_corpus_reports_stale_fail_closed`,
  `test_unreadable_file_excluded_and_still_stale`,
  `test_manifest_without_fetched_at_does_not_make_corpus_fresh`). Reverted.
  The two mutations bind to *different* rules, so neither masks the other.
- **Live CLI sanity** (read-only, no network) against the real `data/history`:
  `{"datasets": 3, "fresh_ms": 51939826, "newest_ms": 1788104382750, "reason": "fresh",
  "stale": false}` — 3 datasets, newest ~14.4 h old, honestly fresh under the 7-day policy.
- **Resource guard:** `ok: true`, `violations: []` (28.9 GB available, disk 10.3 % used).
- **Secret scan (contents):** no `api_key|secret|token|password|passwd` in changed files.
- `/opt/bots/bitget-listener` absent from all changed code — guard intact, untouched.
- **Full suite:** see the battery run recorded with this commit.

## Honest status

The deterministic baseline remains **negative → promotion blocked**. Shadow-only posture,
factor-ontology coverage gate, and the honesty gate are unchanged. This phase adds an
observation that can only ever report *less* confidence (stale) than reality, never more.
No corpus acquired this tick; no signed or unsigned order calls made.

## Next candidate

Wire `evaluate_corpus_freshness` into the observability surface / heartbeat status so a
stale corpus is *visible* and can park heavy evaluation work fail-closed (directive §7 +
§11 automation contract) — the observation now exists but nothing consumes it yet.
Alternatively, extend the factor ontology to fill the still-unrepresented categories
surfaced on the dashboard (directive §3).
