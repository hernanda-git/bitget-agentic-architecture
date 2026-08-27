# Phase 18 — Recursion hardening of the report-truthfulness guard (unblocked)

**Generated (WIB / Asia/Jakarta):** 2026-08-27 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** evaluation-integrity engineering, offline, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `dashboard truthfulness` as an unblocked stream. Phase 17
wired `assert_truthful` into both evaluation entrypoints and its own Limitations
section explicitly named a gap:

> The guard checks the TOP LEVEL of the report dict only... a forbidden key
> buried inside an unrelated nested sub-dict would not be flagged. This is
> currently safe; a future producer that nests selection claims should flatten
> them or the guard should recurse.

This phase closes that gap. `src/evaluation/report_honesty.py` now recurses into
nested dicts and lists so a forbidden `winner` / `promoted` / `go_live_ready` /
`verdict: PASS` / `profitable` / `promotion_gate: POSITIVE` key nested inside a
sub-dict or a list-of-dicts is still caught. A depth cap (`MAX_SCAN_DEPTH = 50`)
guarantees termination on pathological structures.

### Deliberate design choice (pre-validated empirically)

The recursion set deliberately EXCLUDES `selected`. Legitimate evaluation dicts
can carry sub-keys such as `selected_feature` / `selected_strategy`; a nested
`selected` is not, by itself, proof of a selection overclaim. Only the TOP-LEVEL
`selected` is checked (preserved from the previous behavior). Before implementing
I assembled the real `run_strategy_baseline` payload and recursively scanned all
nested keys for membership in the forbidden sets: **0 collisions**, so recursing
the remaining unambiguous keys cannot false-positive on the genuine report.

## TDD cycle (strict)

- **RED:** `tests/test_report_honesty_recursion.py` (11 tests) was written first,
  importing `MAX_SCAN_DEPTH` (did not exist) and asserting nested-overclaim
  behaviors the module did not yet have. Run failed at collection:
  `ImportError: cannot import name 'MAX_SCAN_DEPTH' from 'src.evaluation.report_honesty'`
  (feature absent, not a typo).
- **GREEN:** Added `MAX_SCAN_DEPTH`, `NESTED_FORBIDDEN_PROMOTION_KEYS`, a
  `_scan_node` recursive walker, and a top-level-only `selected` check. The new
  11 tests -> 11 passed. Existing `tests/test_report_honesty.py` (17 tests)
  stayed green, confirming no regression and no double-counting (`selected`
  special-cased at top only).
- **REFACTOR:** None required; the change is a minimal composition of the
  existing overclaim rules plus a bounded recursive walker.

## Raw tests (executed this run)

```text
pytest tests/test_report_honesty_recursion.py -v      -> 11 passed
pytest tests/test_report_honesty.py -v                -> 17 passed
pytest tests/ -q                                       -> 416 passed (was 405; +11 new)
python3 -m compileall -q src scripts tests             -> exit 0 (clean)
```

New tests (11) cover: nested forbidden promotion key; nested key inside a
list-of-dicts; two-level-deep nesting; nested forbidden verdict string;
nested neutral verdict NOT flagged; nested profitable-vs-negative-pnl
contradiction; nested `promotion_gate` while blocked; legitimate nested
fields (`selected_feature`, neutral `verdict`) NOT flagged (no false
positive); a 100-level structure without a forbidden key terminates and reports
nothing; a forbidden key within `MAX_SCAN_DEPTH` is still flagged; a forbidden
key beyond `MAX_SCAN_DEPTH` is not flagged but the call still terminates
(bounded, documented limitation).

## Mutation test (assertions are real, not decoration)

Disabled the nested promotion-key scan (`for key in NESTED_FORBIDDEN_PROMOTION_KEYS:`
-> `for key in ():`), then re-ran the recursion suite:

```text
FAILED test_nested_forbidden_promotion_key_flagged
FAILED test_nested_forbidden_promotion_key_in_list_of_dicts_flagged
FAILED test_nested_two_levels_deep_flagged
FAILED test_deep_chain_within_depth_is_flagged
4 failed, 7 passed
```

The mutation broke exactly the assertions that bind to the nested promotion-key
rule, while the verdict / profitability / promotion_gate / depth-termination
tests (which exercise other rules) remained green. Reverted the mutation ->
11 passed. This proves the recursion assertions test real behavior.

## Network calls

- **0** network requests. The module is pure logic over an in-memory `dict`.

## Signed calls / orders / positions

- **Signed calls: 0. Orders: 0. Positions: 0.** This is evaluation-integrity
  engineering only. No credentials, demo keys, or live keys were used. No signed
  exchange calls, transfers, withdrawals, or funded execution occurred.

## Trades / fees / funding / PnL

- None. The guard performs no trading, fee, funding, or PnL computation; it only
  validates report text for overclaims. No realized or measured PnL was produced
  by this phase.

## Protection / reconciliation

- Not exercised by this phase (it touches no runtime trading state), consistent
  with it being a pure reporting guard. Protection supervision and reconciliation
  read-back remain covered by their own suites, part of the 416 passing tests.

## Limitations (honest)

- The recursion depth is capped at `MAX_SCAN_DEPTH = 50`. A forbidden key nested
  deeper than 50 levels would evade the scan. This is a deliberate, bounded
  trade-off: no legitimate evaluation report nests that deep, and the cap is what
  guarantees termination on adversarial input. The repository's genuine reports
  are 3-6 levels deep.
- `selected` is intentionally excluded from recursion (top-level only) to avoid
  false positives on legitimate `selected_feature` / `selected_strategy` sub-keys.
  A nested `selected: true` is therefore NOT flagged; only a top-level one is.
- The guard remains a fail-closed claim validator, not a schema validator. It
  complements (does not replace) the JSON decision-contract and event-contract
  schemas.
- The guard cannot manufacture honesty it is not handed: it only flags
  CONTRADICTORY or FORBIDDEN claims. It is the producer's responsibility to embed
  `selection_blocked=True`; the recursion now additionally guarantees a nested
  overclaim cannot slip past the top-level-only scan that previously existed.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. The guard now closes the Phase 17 named gap: a
forbidden selection/winner/promotion signal nested anywhere in the report is
caught, not just at the top level. Unblocked research/engineering continues per
the cron mandate.
