# Offline Verification Report — Cron Run 2026-08-26 (Asia/Jakarta)

- Generated (display TZ): 2026-08-26 23:37:15 WIB (UTC+7)
- Branch: `master` (no upstream set; pushed with `-u origin master`)
- Commit author identity: `𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟` <42990222+hernanda-git@users.noreply.github.com> (derived from `gh api user`)
- Mode: fully offline. No live/testnet/demo credentials, no signed calls, no network I/O.

## Scope of this run

The prior cron run left a complete, green TDD cycle (implementation + tests) in the
working tree but had **not committed or pushed**. This run verifies the build
actually runs (build-verification skill), mutation-checks the key fail-closed
assertions, scans for secrets, and commits the verified work. No new trading
features were added; this is verification + safe publication of prior engineering.

## Raw test results

- **Full suite**: `297 passed` (was 296; +1 new integration replay smoke test).
  Command: `.venv/bin/python -m pytest tests/ -q`
- **compileall** (src, scripts, tests): clean, exit 0.
- **Key suites exercised**:
  - `test_canonical_runtime.py` (composition root: paper + fixture-shadow lifecycles)
  - `test_funding_readiness_gate.py` (fail-closed real-funding gate)
  - `test_ledger_identity.py` / `test_ledger_atomicity.py` (canonical identity + atomic event/projection)
  - `test_replay_equality.py` (ledger replay reconciliation equality)
  - `test_safety_surface.py` (repository safety-surface scanner)
  - `test_phase3_evaluation.py` (stress matrix, statistics, hypothesis registry)
  - `test_integration_replay_smoke.py` (build-verification integration replay)

## Build-verification (does it actually run)

- **Entrypoint starts without crashing**: `scripts/run_autonomous_paper.py --mode paper --cycles 24 --symbols BTCUSDT --scenario hold` returned `status=PASS`, `integrity_ok=true`, `signed_calls=0`, `network_calls=0`, `open_positions=[]`, 96 ledger events, 0 duplicates. (Hold scenario chosen so the run ends flat; a pure-enter scenario intentionally leaves the shared FakeExchange position open and is reported via the integrity flag, not a crash.)
- **Integration replay smoke** (`scripts/ci_replay_smoke.py`, driven by `tests/test_integration_replay_smoke.py`): drove the REAL `CanonicalOfflineRuntime` composition root with `FakeProvider` + `FakeExchange` through **120 real-shaped snapshots** (NOW timestamps).
  - crashes: **0**
  - terminal_events: **120/120**
  - orders_placed (ORDER_SUBMITTED ledger events): **42**
  - decision mix: `EXECUTED=42, HELD=16, PARKED=10, REJECTED=52` (4 distinct dispositions — not a degenerate single bucket).
  - ledger_events: **670**.

## Mutation check (assertions are not decoration)

Disabled BOTH guards in `src/market/history.real_funding_readiness` (`if False and ...`).
Re-ran `tests/test_funding_readiness_gate.py`: **3 failed, 1 passed** — the no-funding,
excessive-missing, and evaluator-fails-closed assertions all went RED; the
adequate-coverage test still passed (correctly). File restored from backup; re-run
confirmed **4 passed** (green). This proves the fail-closed funding assertions bind to
real behavior.

## Raw operational facts (offline only)

| Dimension | Value |
|-----------|-------|
| Network calls | 0 |
| Signed calls / orders to live venue | 0 |
| Orders (paper, FakeExchange) | 42 in replay smoke; 0 in hold entrypoint |
| Positions | paper-only; flattened at end of replay; 0 open at end of hold run |
| Trades / fills | simulated paper fills only |
| Fees | modeled (`FakeExchange` `fee_bps`) |
| Funding | modeled; `real_funding` gate fails closed when coverage absent (verified) |
| PnL | modeled; deterministic baseline is **negative** → `promotion_allowed=False` (`NEGATIVE_NET_PNL`) |
| Protection | `PROTECTION_VERIFIED` events emitted in replay; `verify_protection` checked |
| Reconciliation | `POSITION_RECONCILED` events; `reconcile_positions` in_sync |
| Secret scan (tracked files) | **0 hits** |
| `.env` / `.hermes/` | git-ignored (confirmed via `git check-ignore`) |

## Phase gate status

- **Phase 6 (bounded LLM selection) and all promotion actions: BLOCKED.** The
  deterministic baseline remains negative; no strategy is selected, ranked, or
  promoted. `selection_blocked=True` is emitted by `run_strategy_attribution`.
- All unblocked engineering from the prior run (ledger identity/atomicity,
  replay equality, funding-readiness gate, canonical runtime, safety-surface
  scanner, evaluation stress/statistics/hypotheses, phase-3 evaluation) is now
  verified and committed.

## Limitations (honest)

- Entirely offline measurement. No live, testnet, or demo execution; demo probe
  scripts are quarantined under `quarantine/demo-probes/` and excluded from the
  normal safety surface.
- Synthetic evaluation series use modeled fees/funding/slippage; the
  cost-coverage and funding-readiness gates are fail-closed but were exercised on
  synthetic fixtures, not a real funded dataset.
- Green tests + passing replay do **not** constitute proven profitability; the
  deterministic promotion gate remains the only thing that can unblock Phase 6,
  and it is currently negative.
- The run did not alter policy files, credentials, or the deployed
  `/opt/bots/bitget-listener` tree (never accessed).
