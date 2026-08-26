# Phase 6, bounded paper research operation

## Result

`PASS_WITH_LIMITATIONS`. The canonical launcher now runs bounded offline paper mode through `scripts/northline_agentic_demo.py`, writes durable SQLite-backed run reports, and fails closed unless the explicit demo confirmation is present.

## Exact verification evidence

- Focused tests: `pytest -q tests/test_run_report.py tests/test_restart_recovery.py tests/test_autonomous_paper_cli.py tests/test_service_hygiene.py` -> **22 passed**.
- Full suite: `pytest -q` -> **314 passed**.
- Compile check: `python3 -m compileall -q src scripts` -> **PASS**.
- Resource guard: `python3 scripts/resource_guard.py --json` -> **ok: true**, no violations. Snapshot included ~1.406 GB available memory, 89.048% swap used, and 43.080% disk used.

## Canonical offline runs

Both commands used `DEMO_EXECUTION_CONFIRM=I_UNDERSTAND_DEMO_EXECUTION`, `FakeExchange`, temporary SQLite ledgers, and temporary report directories.

- HOLD: run `ce3548f9d468`, 1/1 cycles, 4 ledger events, 0 orders, 0 network calls, 0 signed calls, no open positions, replay exit 0.
- ENTER: run `d9713df503d9`, 1/1 cycles, 12 ledger events, 2 fake orders, 0 network calls, 0 signed calls, no open positions, fees `0.020999999999999998`, fee-inclusive net PnL `1.957`, replay exit 0. Protection was verified and reconciliation was in sync.

Reports include run ID, Asia/Jakarta timestamp, raw ledger counts, rejection codes, degraded states, provider latency/failure fields, duplicate-prevention evidence, protection/reconciliation evidence, fee-inclusive outcome, anomalies, resource snapshot, and next gate.

## Recovery and safety

Restart recovery parks on reconciliation drift, an active kill switch, or provider outage, and marks interrupted cycles recoverable. Fake exchange duplicate client IDs are idempotent and do not create a second order. Existing protection, partial-fill, kill-switch, provider-circuit, and reconciliation tests remain green.

No public evaluation, signed execution, live/demo exchange, credentials, transfers, or withdrawals were used.

## Limitations

- Explicit confirmation remains mandatory for canonical paper mode and is fail-closed.
- One-cycle smoke runs are `STARTING` for runtime variation because that monitor requires three samples.
- The provider fields are wired, but the canonical fake provider reports zero failures and zero measured latency.
- Crash-stage coverage is bounded offline recovery/idempotency coverage, not a live-process crash test.

Next gate: `RESEARCH_GATE`.
