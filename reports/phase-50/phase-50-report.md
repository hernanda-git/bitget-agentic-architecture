# Phase 50 — Wire corpus-freshness into the observability surface (TDD + mutation-verified)

**Date:** 2026-08-31
**Author:** valarion (42990222+hernanda-git@users.noreply.github.com)
**Discipline:** TDD + mutation-verified, fail-closed, offline, no signed/order calls.
**Bounded phase source:** the "Next candidate" explicitly deferred by Phase 49 —
"Wire `evaluate_corpus_freshness` into the observability surface / heartbeat status
so a stale corpus is *visible* and can park heavy evaluation work fail-closed
(directive §7 + §11 automation contract)."

## Summary

Phase 49 landed the fail-closed `evaluate_corpus_freshness` observation but nothing
consumed it. This phase wires it into `scripts/heartbeat_status.assemble_status()` so
the staleness of the blessed public-history corpus is now **visible on the
observability dashboard** and exposes a single `stale` flag a scheduler can read to
park heavy evaluation work fail-closed.

The observation itself is delegated unchanged (Phase 49, mutation-verified). This phase
adds exactly one thin, honest pass-through:

- `_corpus_freshness(corpus_dir, *, now_ms=None)` in `heartbeat_status.py` — returns
  `evaluate_corpus_freshness(...).as_dict()`; on any observation error it fails closed
  to `{"present": False, "stale": True, "reason": "unavailable"}` (we cannot prove
  freshness, so we never invent "fresh").
- `assemble_status()` now includes a top-level `"corpus_freshness"` key carrying
  `present, datasets, newest_ms, oldest_ms, max_age_ms, stale, reason, fresh_ms` —
  symmetric with the existing `resource_guard` / `factor_ontology` sections.

No trading/research logic touched. No promotion claim. `data/history` is read-only and
untouched.

## Changes

- `scripts/heartbeat_status.py`: add `DEFAULT_CORPUS_DIR`, import
  `evaluate_corpus_freshness` / `DEFAULT_MAX_AGE_MS`, add `_corpus_freshness()`,
  add `"corpus_freshness": _corpus_freshness(DEFAULT_CORPUS_DIR)` to `assemble_status()`.
- `tests/test_heartbeat_status.py`: 4 new tests.
- `reports/phase-50/phase-50-report.md`: this report.

## Verification

- `python -m compileall -q src scripts` → clean (`COMPILE_OK`).
- **RED proven first:** the 4 new tests failed before implementation
  (`ImportError: cannot import name '_corpus_freshness'`; and
  `assert 'corpus_freshness' in status` — a genuine behavioral gap, not a typo).
- **GREEN:** `python -m pytest tests/test_heartbeat_status.py -k corpus_freshness`
  → **4 passed**.
- **Full suite:** baseline 655 passed / 4 skipped / 0 failed
  (pre-change) → **659 passed / 4 skipped / 0 failed** (post-change, +4 new).
- **Mutation checks (all reverted after confirming RED):**
  1. *Wiring* — removed `"corpus_freshness": ...` from `assemble_status()` →
     `test_assemble_status_surfaces_corpus_freshness` RED (`'corpus_freshness' in ...`).
  2. *Honest delegation* — flipped the return to `{**as_dict(), "stale": False,
     "reason": "fresh"}` → both `test_corpus_freshness_missing_reported_stale_fail_closed`
     and `test_corpus_freshness_fresh_and_stale` RED (would launder stale→fresh; the
     exact honesty failure this gate must catch).
  3. *Fail-closed fallback* — flipped `stale: True` → `stale: False` in the
     `except` branch → `test_corpus_freshness_unavailable_falls_back_fail_closed` RED.
- **Live sanity** (read-only, no network) against the real `data/history`:
  `{"datasets": 3, "fresh_ms": 73689531, "newest_ms": 1788104382750, "reason":
  "fresh", "stale": false}` — 3 datasets, newest ~14.4 h old, honestly fresh under the
  7-day policy.
- **Resource guard:** `ok: true`, `violations: []` (28.2 GB available, disk 10.3 % used).
- **Secret scan (contents):** only prose matches ("No secrets", test-name/assertion
  strings); no credential.
- `/opt/bots/bitget-listener`: present only as the pre-existing guard-reference lines
  in `heartbeat_status.py`/`test_heartbeat_status.py`; no new reference added, never
  read or modified.

## Honest status

The deterministic baseline remains **negative → promotion blocked**. Shadow-only posture,
factor-ontology coverage gate, and the honesty gate are unchanged. This phase makes an
existing fail-closed observation *visible*; it can only ever report *less* confidence
(stale) than reality, never more. No corpus acquired this tick; no signed or unsigned
order calls made.

## Next candidate

A consumer that actually *acts* on `corpus_freshness.stale` to park heavy evaluation work
fail-closed (directive §11 automation contract) — e.g. a `should_park_heavy_work(status)`
predicate, or gating the evaluate step in the cron entrypoint on `stale is True`.
Alternatively, extend the factor ontology to fill the still-unrepresented categories
surfaced on the dashboard (directive §3).
