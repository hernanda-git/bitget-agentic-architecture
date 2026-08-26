# Phase 2 summary

- Status: `PASS`
- Timestamp: `2026-08-26T23:25:07+07:00`, timezone `Asia/Jakarta`
- Scope: ledger identity, atomic event/projection writes, and offline replay equality.

## Work units

- `2.1`: `append_event` and `append_event_with_projection` reject implicit canonical identity. Required runtime identity is `cycle_id`, `trace_id`, `mode`, `product_type`, `symbol`, and timestamp (`created_ms`, with `timestamp` accepted as an input alias). Canonical payload hashes are persisted. `append_legacy` is the explicitly named compatibility adapter for historical fixtures. The paper and fixture-shadow runtime paths use `append_event` with explicit identity.
- `2.2`: Event and projection insertion share one SQLite transaction. Explicit rollback is executed on injected or database faults. The fault test proves both event and projection rows remain absent.
- `2.3`: Replay now reconstructs terminal dispositions, positions, protection, reconciliation, breaker state, fees, funding, and PnL. `assert_replay_equal` raises `ReplayMismatch` on any drift, including financial values.

## Exact verification commands and raw outcomes

1. `python3 -m pytest -q tests/test_ledger_identity.py tests/test_ledger_atomicity.py tests/test_replay_equality.py tests/test_paper_runtime.py tests/test_canonical_runtime.py`
   - Initial TDD result: `RED`, collection failed because the new replay and legacy symbols did not exist.
   - Final result: `17 passed`.
2. `python -m pytest -q tests/test_ledger.py tests/test_ledger_schema.py tests/test_ledger_summary.py tests/test_phase1_ledger.py tests/test_replay.py tests/test_paper_runtime.py tests/test_canonical_runtime.py`
   - Result: `32 passed`.
3. `python -m pytest -q`
   - Result: `293 passed in 8.28s`.
4. `python3 -m compileall -q src scripts tests`
   - Result: exit `0`.
5. `python3 scripts/resource_guard.py --json`
   - Result: `ok: true`, violations `[]`.
6. Offline repository-root smoke:
   - `python scripts/run_autonomous_paper.py --mode paper --cycles 1 --symbols BTCUSDT --scenario enter --ledger /tmp/phase2-ledger.sqlite3 --reports-dir /tmp/phase2-run`
   - `python scripts/replay_ledger.py /tmp/phase2-ledger.sqlite3`
   - Result: `PASS`; runtime/replay assertions matched `EXECUTED`, zero open positions, fees `0.020999999999999998`, funding `0.022`, net PnL `1.957`.

## Offline fake execution counts

- Network calls: `0`
- Signed calls: `0`
- Orders: `2` (entry and protective exit)
- Open positions: `0`
- Closed trades: `1`

## Limitations and next gate

`RuntimeEvent.from_dict` remains tolerant for historical object fixtures and computes a missing hash, while canonical ledger writes persist the canonical hash. The old `append` spelling remains an alias for `append_legacy` to preserve existing callers, so new runtime code must use `append_event` or `append_event_with_projection`. Replay is offline only and does not exercise exchange/network or funded execution. The direct `AutonomousPaperRuntime` path was corrected after worker verification so its events also carry explicit identity.

Next gate: Phase 3 public-data hardening and funding-readiness gating. Demo and funded execution remain blocked.
