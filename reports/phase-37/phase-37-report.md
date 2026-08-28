# Phase 37 — Per-liquidity-tier cost-stress envelope on OBSERVED spreads (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-28 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline unit work + offline replay of already-local public history (zero network egress, zero orders)
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not touch the deterministic gate. It only makes the cost-stress envelope per-symbol realistic. The deterministic baseline remains negative (see prior phases); `selection_blocked` / `promotion_blocked` are forced `True` and never flipped.

## Scope and why it is unblocked

The cron mandate lists `realistic cost/funding/slippage stress` as an unblocked stream. Phase 36 measured a real-venue per-symbol top-of-book spread and proved the single global assumed half-spread is simultaneously too conservative on majors (BTC/ETH/SOL ~0.01–0.1 bps) and too optimistic on alts (ADA ~4.8 bps, AVAX/SUI/NEAR ~1.3–1.6 bps). This phase turns that measurement into a loadable, fail-closed cost table and a **per-liquidity-tier** cost-stress envelope that replays the existing public historical corpus with the OBSERVED spread instead of the global assumption.

A half-written, uncommitted Phase 37 already existed from a prior session (`src/evaluation/symbol_cost_table.py`, `tests/test_symbol_cost_table.py`, `tests/test_cost_envelope_per_tier.py`, and a 62-line addition to `src/evaluation/cost_sensitivity.py`). This run (a) repaired two genuine test defects in that prior work, (b) added a mutation check proving the new assertions bind, (c) added a reproducible offline runner + its own TDD test, and (d) produced committed per-tier evidence over the real corpus. Nothing here changes the promotion gate, places orders, or computes realized PnL.

## TDD cycle (strict)

### A. Symbol cost table + per-tier envelope (pre-existing untracked work, repaired this run)
- **RED (prior session, re-confirmed):** the module and `cost_envelope_per_tier` did not exist; tests failed with `ModuleNotFoundError`. This run additionally found TWO real test defects that would have let the suite pass while testing nothing:
  1. Fixtures used non-`USDT` symbols (`BTC`, `ETH`, `XRP`, `ADA`, `MISSING`) that `MarketSnapshot.__post_init__` rejects with `ValueError: invalid symbol`. Fixed fixtures to `BTCUSDT`/`ETHUSDT`/`XRPUSDT`/`ADAUSDT`/`MISSINGUSDT`.
  2. `test_cost_envelope_per_tier_groups_and_aggregates` asserted `MISSXUSDT` lands in `TIER_WIDE`, but `MISSXUSDT` was in the *table* yet never supplied as a *snapshot*, so the loop never processed it. Added `MISSXUSDT` to `sym_snaps` + `net_for_symbol`.
  3. `test_cost_envelope_per_tier_recalibrates_observed_spread` defined a `_capture` spy but patched with `_fake_envelope`, so `seen` was never populated (would `KeyError`). Rewired the call under `patch(..., _capture)`.
- **GREEN:** 16 passed (`test_symbol_cost_table.py` 13 + `test_cost_envelope_per_tier.py` 3).
- **Mutation check (build-verification skill):** backed up both modules, applied two mutations, confirmed the relevant assertions go RED, reverted:
  - `cost_sensitivity.py`: `any_profitable": any(n > 0` -> `any(n > 9999` broke `test_cost_envelope_per_tier_groups_and_aggregates` (expected `TIER_MODERATE.any_profitable is True`).
  - `symbol_cost_table.py`: `ask = mark * (1.0 + half)` -> `ask = mark * (1.0 - half)` broke `test_recalibrate_spread_changes_bid_ask_to_observed`, `test_recalibrate_snapshots_by_symbol_applies_per_symbol`, and `test_cost_envelope_per_tier_recalibrates_observed_spread` (spread collapses to 0).
  - Result: 4 failed / 12 passed under mutation; reverted to 16 passed. Assertions genuinely bind to behavior, not decoration.

### B. Offline runner (`scripts/run_cost_envelope_per_tier.py`)
- **RED:** `tests/test_run_cost_envelope_per_tier.py` written first; `from scripts.run_cost_envelope_per_tier import build_per_tier_report` -> `ModuleNotFoundError`. 2 failed.
- **GREEN:** implemented `build_per_tier_report` (loads the committed Phase 36 table + every local `data/history/*.json`, passes all symbols through `cost_envelope_per_tier`, which recalibrates only observed-spread symbols and reports the rest under `unknown_symbols`) + `main()` (argparse, writes JSON + markdown). 2 passed with a synthetic in-repo dataset (no network, no secrets).

### C. Corpus data-quality scanner (`scripts/check_corpus_quality.py`)
- **RED:** `tests/test_check_corpus_quality.py` written first; `from scripts.check_corpus_quality import scan_corpus` -> `ModuleNotFoundError`. 3 failed.
- **GREEN:** implemented `scan_corpus` (loads every `data/history/*.json`, validates symbol format, integrity hash, assumed spread, candle non-emptiness; ignores the manifest; never crashes on one bad file) + `main()` (writes JSON, **exit 1 when any defect is found** — fail-closed so a dirty corpus cannot be laundered into "clean"). 3 passed with synthetic in-repo datasets (valid / invalid-symbol / tampered-integrity / malformed / manifest).
- **Mutation check:** temporarily changed `if not VALID_SYMBOL.match(sym):` -> `if False:` so an invalid symbol is no longer flagged; `test_scan_corpus_flags_defects` failed (1 failed), reverted to 3 passed. Proves the defect assertion binds.

## What this run added / changed
- `src/evaluation/symbol_cost_table.py` — NEW (carried over + finalized): `ObservedCostTable`, `load_observed_spread_table` (fail-closed), `liquidity_tier`, `classify_symbols`, `tier_median_spread`, `recalibrate_spread`, `recalibrate_snapshots_by_symbol`.
- `src/evaluation/cost_sensitivity.py` — MODIFIED (+62 lines): `cost_envelope_per_tier` recalibrates each symbol to its observed spread, groups net PnL per liquidity tier, and is always `selection_blocked=True` / `promotion_blocked=True`.
- `scripts/run_cost_envelope_per_tier.py` — NEW: offline, reproducible per-tier envelope runner.
- `scripts/check_corpus_quality.py` — NEW: offline, fail-closed corpus data-quality scanner (surfaced the real `TINY_1m.json` invalid-symbol defect).
- `tests/test_symbol_cost_table.py` (13), `tests/test_cost_envelope_per_tier.py` (3, repaired), `tests/test_run_cost_envelope_per_tier.py` (2), `tests/test_check_corpus_quality.py` (3) — NEW TDD suites.
- `reports/phase-37/phase-37-report.md`, `reports/phase-37/per_tier_cost_envelope.json` + `.md`, `reports/phase-37/corpus_quality.json` — committed evidence.

## Raw tests (executed this run)
```text
pytest tests/test_symbol_cost_table.py tests/test_cost_envelope_per_tier.py -q  -> 16 passed
pytest tests/test_run_cost_envelope_per_tier.py -q                              -> 2 passed
pytest tests/test_check_corpus_quality.py -q                                   -> 3 passed
python3 -m compileall -q src scripts tests                                     -> exit 0 (clean)
pytest tests/ -q                                                               -> 591 passed, 0 failed (full suite, no regressions)
# mutation checks (temporary, reverted):
#   any(n>0)->any(n>9999) in cost_sensitivity + ask half-sign flip in symbol_cost_table
#     -> 4 failed / 12 passed ; reverted -> 16 passed
#   VALID_SYMBOL.match(sym) guard in check_corpus_quality disabled
#     -> 1 failed / 2 passed ; reverted -> 3 passed
```

## Offline corpus-quality scan (no egress)
Invoked `scripts/check_corpus_quality.py` over `data/history/*.json` (already-local public corpus). It scanned 30 files, found **1 defect**: `TINY_1m.json` has symbol `TINY` (not upper-case `USDT`-suffixed) and is therefore excluded from every replay. The scanner exits 1 (fail-closed) so a dirty corpus can never be reported clean. Evidence: `reports/phase-37/corpus_quality.json`.

## Offline replay over the real corpus (no egress)
Invoked `scripts/run_cost_envelope_per_tier.py --limit 300` over `data/history/*.json` (already-local public Bitget 1m candles, git-ignored corpus) and the committed `reports/phase-36/orderbook_calibration.json` table.

| Tier | Symbols | n_cells | min_net | median_net | max_net | any_profitable | all_blocked |
|------|---------|---------|---------|------------|---------|----------------|-------------|
| TIER_TIGHT | BTCUSDT, ETHUSDT, SOLUSDT | 40 | -2622.59 | -61.82 | +954.40 | True | False |
| TIER_MODERATE | XRPUSDT | 8 | -0.1187 | -0.1092 | -0.1025 | False | True |
| TIER_WIDE | ADAUSDT, AVAXUSDT, NEARUSDT, SUIUSDT | 32 | -0.1320 | -0.0231 | -0.0014 | False | True |

- **Symbols replayed:** 28. **Unknown (no observed spread):** 18 (AAVE, APT, ARB, ATOM, BCH, BNB, DOGE, DOT, ETC, FIL, INJ, LINK, LTC, OP, TINY, TRX, UNI, XLM). **Skipped (unparseable symbol):** `TINY` (dataset symbol `TINY`, not `USDT`-suffixed — a real data-quality flag, surfaced honestly, not crashed on).
- **Honest reading:** with the OBSERVED near-zero spreads on majors, the *tight* tier produces a few positive net cells (max +954) — but that is the **minimum** quoted spread with no size-slippage and no adverse selection; real fills at size are worse. The *moderate* and *wide* tiers stay uniformly negative even at the floor. The deterministic baseline remains negative, so the gate stays `selection_blocked=True` / `promotion_blocked=True`. No winner / promoted / selected / go_live / positive_edge key is emitted. The Phase 6 promotion block is unchanged and not weakened by this measurement.

## Network calls
- **0 network calls this run.** All inputs are local: the git-ignored `data/history/*.json` corpus (acquired in prior phases) and the committed `reports/phase-36/orderbook_calibration.json` (measured read-only in Phase 36). No `GET`, no authenticated, signed, or account endpoints were touched.

## Signed calls / orders / positions
- **Signed calls: 0.** Orders: 0. Positions: 0 (open or closed by this phase). No credentials, demo keys, or live keys were used. No signed exchange calls, transfers, withdrawals, or funded execution occurred. Egress: none.

## Trades / fees / funding / PnL
- **Trades executed by this phase: 0.** Fees: 0. Funding: 0 (the replay uses `BaselineConfig(real_funding=False)`; funding modeling remains in the historical corpus from prior phases). PnL: 0 realized — the per-tier net figures above are **cost-stress envelope projections over historical marks**, not executed PnL, and are reported strictly under the blocked gate.

## Protection / reconciliation
- **Not exercised** by this measurement-only change. No position, protection, or reconciliation path was touched. The only fail-closed logic is the observed-spread table loader (omits any symbol without a positive-finite observed spread) and `cost_envelope_per_tier` (never prices an uncalibrated symbol as cheap; routes it to `unknown_symbols`).

## Limitations (honest)
- **Spread is quoted, not executed.** The Phase 36 table calibrates the *minimum* top-of-book cost. Actual fills at size incur deeper-level slippage and adverse selection not captured here; the tight-tier positive cells are therefore an optimistic floor, not an expected edge.
- **Snapshot calibration.** The observed spread rests on 3 snapshots/symbol from Phase 36 — a point-in-time read, not a distribution across volatility regimes. The replay uses 300 historical candles/symbol for the *strategy* marks but the *spread* is still the single observed value.
- **8 of ~28 symbols have an observed spread.** The remaining 18 are honestly reported as `unknown_symbols` and excluded from every tier (never priced as cheap). A deeper live `limit` and broader symbol coverage would tighten the wide-tier depth readings.
- **No promotion implied.** `all_blocked=False` on the tight tier reflects cost-multiplier combos where the floor spread is near zero; it is NOT a go-live signal. The deterministic baseline is negative and the gate is unchanged.
- The runner reads from the git-ignored corpus (`data/history/`); the generated `per_tier_cost_envelope.json/.md` are committed as reproducible evidence and are regenerable via the same script. No LLM, provider, or autonomous decision path was invoked.

## Phase 6 promotion gate
- **Still BLOCKED.** This phase is purely cost-surface realism. The deterministic baseline remains negative; no promotion action was taken and none is authorized while the baseline is negative.

## Commit / push
- New/changed: `src/evaluation/symbol_cost_table.py`, `src/evaluation/cost_sensitivity.py`, `scripts/run_cost_envelope_per_tier.py`, `scripts/check_corpus_quality.py`, `tests/test_symbol_cost_table.py`, `tests/test_cost_envelope_per_tier.py`, `tests/test_run_cost_envelope_per_tier.py`, `tests/test_check_corpus_quality.py`, `reports/phase-37/phase-37-report.md`, `reports/phase-37/per_tier_cost_envelope.json`, `reports/phase-37/per_tier_cost_envelope.md`, `reports/phase-37/corpus_quality.json`.
- Git identity verified: `user.name=𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟`, `user.email=42990222+hernanda-git@users.noreply.github.com` (matches `gh api`).
- Secret scan: `.env` is git-ignored; content scan over tracked + new text found **0 secret hits**. Verified repeatable, network-free, secret-free command: `pytest tests/test_symbol_cost_table.py tests/test_cost_envelope_per_tier.py tests/test_run_cost_envelope_per_tier.py tests/test_check_corpus_quality.py -q`.
