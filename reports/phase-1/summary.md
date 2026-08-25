# Phase 1 Summary: Ledger Trust Spine

## Result

`PASS`. All Phase 1 gate criteria were verified in the standalone repository. No network calls or orders were made. `/opt/bots/bitget-listener` was not accessed or modified, and the existing `.hermes/` plan state was left untouched.

## Delivered

- Added canonical `RuntimeEvent` validation with complete runtime identity, bounded canonical payload hashing, schema versioning, and immutable run metadata fields.
- Reworked `EventLedger` to use WAL, foreign keys, a 10-second busy timeout, and explicit versioned migration evidence in `schema_migrations`.
- Added atomic `append_event_with_projection(...)` transaction support. Fault injection verified that an exception rolls back both event and projection.
- Added required durable ledger queries: latest cycle, disposition counts, open and closed positions/trades, realized PnL, fees, funding, protection status, reconciliation status, active breakers, recent events, and runtime status.
- Retained old offline callers only through canonical event construction and validation. Unknown event types are rejected.
- Repaired direct execution of `scripts/replay_ledger.py` by adding repository-root import hygiene.
- Added `tests/test_phase1_ledger.py` with focused contract, transaction rollback, SQLite pragma/migration, query, and direct-script tests.

## TDD evidence

1. Initial focused RED: `python -m pytest tests/test_phase1_ledger.py -q` returned `5 failed` because the requested metadata, transaction API, WAL, and queries were absent.
2. Direct-script RED: `python -m pytest tests/test_phase1_ledger.py::test_replay_script_runs_directly_from_repository_root -q` returned `1 failed` with `ModuleNotFoundError: No module named 'src'`.
3. GREEN: `python -m pytest tests/test_phase1_ledger.py -q` returned `6 passed in 0.14s`.

## Verification commands and raw results

| Command | Exit | Result |
|---|---:|---|
| `python3 -m pytest tests/test_event_contracts.py tests/test_ledger.py -q` | 0 | `8 passed in 0.05s` |
| `python3 -m pytest tests/test_ledger_schema.py tests/test_restart_recovery.py -q` | 0 | `6 passed in 0.11s` |
| `python3 -m pytest tests/test_ledger_summary.py -q` | 0 | `2 passed in 0.07s` |
| `python3 -m pytest tests/test_service_hygiene.py -q` | 0 | `5 passed in 0.43s` |
| `python3 -m pytest tests/test_phase1_ledger.py -q` | 0 | `6 passed in 0.14s` |
| `python3 -m pytest -q` | 0 | `159 passed in 4.49s` |
| `python3 -m compileall -q src scripts tests` | 0 | no output |
| `git diff --check` | 0 | no output |
| `python3 scripts/replay_ledger.py /tmp/phase1-empty-ledger.sqlite3` | 0 | `{"dispositions": {}, "positions": {}, "protection": {}, "reconciliation": "UNKNOWN", "risk_breaker": "CLOSED"}` |
| `python3 scripts/review_run.py --help` | 0 | usage displayed |
| `python3 scripts/run_autonomous_paper.py --help` | 0 | usage displayed |
| `python3 scripts/run_autonomous_shadow.py --help` | 0 | usage displayed |

## Files changed

- `src/ledger/events.py`
- `src/ledger/models.py`
- `src/ledger/sqlite.py`
- `scripts/replay_ledger.py`
- `tests/test_phase1_ledger.py`
- `reports/phase-1/summary.json`
- `reports/phase-1/summary.md`

## Blockers

None.
