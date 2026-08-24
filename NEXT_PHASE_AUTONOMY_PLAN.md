# Autonomous Runtime Phase Plan

> **For Hermes:** Execute this plan task-by-task inside `/root/bitget-agentic-architecture`. Do not ask the user for per-step approval. Use the existing `test-driven-development`, `responsive-web-verification`, `secure-trading-bot-dev`, and `bitget-listener-ops` skills where applicable. Keep the entire implementation standalone.

**Plan file:** `/root/bitget-agentic-architecture/NEXT_PHASE_AUTONOMY_PLAN.md`

**Goal:** Turn the standalone scaffold into a durable, replayable, autonomous demo trading runtime with a single truth spine from market observation to provider decision, policy disposition, paper/demo execution, protection, reconciliation, ledger, and read-only UI projection.

**Operating rule:** No human approval per trade. The runtime makes normal `ENTER`, `EXIT`, `REDUCE`, `HOLD`, and `CANCEL` decisions automatically. Deterministic policy, kill switch, protection, and reconciliation remain machine-enforced constitutional controls.

**Safety boundary:** Never modify, restart, import, deploy, or read credentials from `/opt/bots/bitget-listener`. Never use `USDT-FUTURES` in this project. The only accepted venue product is `SUSDT-FUTURES`, and the only signed demo execution path may use the separately stored demo credential in the standalone `.env`.

---

## Current verified baseline

The project currently has:

- standalone directory: `/root/bitget-agentic-architecture`
- commit provenance established locally
- provider interface and Anthropic adapter
- strict JSON decision parser
- normalized market snapshots and freshness gate
- public Bitget demo market adapter
- autonomous cycle runner
- deterministic sizing
- durable kill switch
- fake exchange
- SQLite event ledger
- reconciliation and protection primitives
- durable `PaperLoop`
- read-only demo dashboard `Northline Operations Desk`
- read-only demo server at `scripts/ui_server.py`
- 74 passing tests
- browser verification at 390px, 768px, and 1440px with no horizontal overflow
- demo account verified and flat after one micro smoke order
- venue preset SL/TP observed empty on the demo smoke order, therefore protection is currently `DEGRADED` until a bot-side supervisor is integrated

The next phase must close the gap between isolated components and an autonomous runtime.

---

# Phase A, make the ledger the system of record

## A1. Expand the ledger schema

**Files:**

- Modify: `src/ledger/sqlite.py`
- Create: `src/ledger/models.py`
- Create: `tests/test_ledger_schema.py`

Add durable tables or equivalent event indexes for:

- `cycles`
- `orders`
- `fills`
- `positions`
- `protection`
- `reconciliation`
- `runtime_state`

Every row must carry:

```text
cycle_id
trace_id
created_ms
mode
product_type
symbol
payload_hash
schema_version
```

Add unique constraints for:

- `cycle_id`
- `client_order_id`
- `venue_order_id` when available
- `fill_id` when available

Add migrations that work on an existing SQLite file. Never depend on `CREATE TABLE IF NOT EXISTS` alone for new columns.

## A2. Define typed event contracts

**Files:**

- Create: `src/ledger/events.py`
- Create: `schemas/runtime-event.schema.json`
- Create: `tests/test_event_contracts.py`

Define typed events:

```text
MARKET_OBSERVED
CONTEXT_BUILT
AGENT_DECISION
DECISION_REJECTED
INTENT_APPROVED
ORDER_SUBMITTED
ORDER_ACKNOWLEDGED
FILL_OBSERVED
PROTECTION_REQUESTED
PROTECTION_VERIFIED
PROTECTION_FAILED
POSITION_RECONCILED
RECONCILIATION_DRIFT
CIRCUIT_BREAKER
KILL_SWITCH
CYCLE_TERMINAL
```

Reject unknown event types, missing cycle identity, missing timestamps, invalid hashes, and unbounded payloads.

## A3. Add ledger-derived summaries

**Files:**

- Modify: `src/ledger/sqlite.py`
- Create: `tests/test_ledger_summary.py`

Expose functions:

```python
latest_cycle()
disposition_counts()
open_positions()
latest_protection_status()
latest_reconciliation_status()
recent_events(limit=50)
runtime_status()
```

The UI and runtime must read summaries from these functions rather than reconstructing state from fixture text.

### Acceptance gate A

- Reopening SQLite preserves cycle, event, order, fill, protection, and reconciliation state.
- Duplicate cycle and order IDs cannot create duplicate rows.
- A crash between any two event writes can be recovered by replaying the event stream.
- All payloads are JSON-serializable and bounded.

---

# Phase B, complete the autonomous paper runtime

## B1. Build `AutonomousPaperRuntime`

**Files:**

- Create: `src/runtime/paper_runtime.py`
- Create: `tests/test_paper_runtime.py`

The runtime must own the complete loop:

```text
MarketSnapshot
  -> cycle claim
  -> freshness gate
  -> context build
  -> provider call
  -> strict parse
  -> policy validation
  -> sizing
  -> intent creation
  -> fake execution
  -> fill read-back
  -> protection supervisor
  -> reconciliation
  -> terminal disposition
```

The runtime must not expose a raw `place_order` method to the provider.

## B2. Add provider circuit behavior

**Files:**

- Modify: `src/providers/ports.py`
- Modify: `src/providers/anthropic.py`
- Create: `src/providers/circuit.py`
- Create: `tests/test_provider_circuit.py`

Required behavior:

- timeout -> `NO_DECISION`
- malformed output -> `NO_DECISION`
- repeated failures -> `PARKED_PROVIDER`
- circuit recovery requires a fresh successful health call
- provider cannot clear kill switch
- provider cannot change policy
- provider cannot request arbitrary tools

## B3. Add bounded cadence and scheduler

**Files:**

- Create: `src/runtime/scheduler.py`
- Create: `tests/test_scheduler.py`

The scheduler must:

- enforce one active cycle per symbol
- enforce maximum cycle frequency
- coalesce duplicate snapshots
- stop new entries when the kill switch, provider circuit, or reconciliation breaker is active
- continue protection and reconciliation while entries are parked
- survive a clean restart
- shut down cleanly without dropping an event

Use an explicit event queue. Do not build an uncontrolled prompt loop.

## B4. Add replay mode

**Files:**

- Create: `scripts/replay_ledger.py`
- Create: `tests/test_replay.py`

Replay must rebuild:

- cycle dispositions
- paper positions
- protection state
- reconciliation state
- risk breaker state

Replay output must match the stored terminal state. A mismatch is a failed integrity check.

### Acceptance gate B

- Valid `ENTER` produces one complete paper trace.
- `HOLD` produces no order.
- stale data produces no provider call and no order.
- provider failure produces no order.
- policy rejection produces no order.
- kill switch produces no new entry but keeps reconciliation alive.
- duplicate snapshot after restart produces no second order.
- crash after intent creation does not duplicate a client order.
- replay reproduces the same terminal state.

---

# Phase C, protection supervisor

## C1. Define protection state machine

**Files:**

- Create: `src/protection/models.py`
- Create: `src/protection/supervisor.py`
- Create: `tests/test_protection_supervisor.py`

States:

```text
NOT_REQUIRED
PENDING
PROTECTED
DEGRADED
UNKNOWN
EMERGENCY_EXIT_PENDING
CLOSED
```

Rules:

- A new position starts as `PENDING`.
- Only venue read-back or a separately verified bot-side monitor may produce `PROTECTED`.
- Missing SL or TP produces `DEGRADED`.
- `DEGRADED` activates entry parking.
- `UNKNOWN` activates entry parking.
- Protection checks continue during provider outage.
- Protection logic never depends on the LLM.

## C2. Add bot-side mark monitor for demo

**Files:**

- Create: `src/protection/mark_monitor.py`
- Create: `tests/test_mark_monitor.py`

The monitor must:

- consume fresh mark prices
- preserve exact intended SL/TP levels
- handle long and short positions
- trigger close once, idempotently
- persist armed protection
- restore armed protection after restart
- detect stale price feed
- park new entries when stale
- generate `PROTECTION_FAILED` or `EMERGENCY_EXIT_PENDING` events

It must never widen a stop. It must never flip a side.

## C3. Protection reconciliation

**Files:**

- Modify: `src/reconcile/engine.py`
- Create: `tests/test_protection_reconciliation.py`

Compare:

```text
intended SL/TP
venue SL/TP
bot-side armed SL/TP
current mark
liquidation price
```

Reject a position as protected if the venue is missing levels and the bot-side monitor is not armed and fresh.

### Acceptance gate C

- Normal paper position with protection -> `PROTECTED`.
- Missing venue protection -> `DEGRADED` or bot-side `PROTECTED` only after monitor verification.
- Restart restores protection state.
- Stale feed prevents new entries and raises an event.
- A stop breach produces one close intent, not duplicate closes.
- Liquidation price on the wrong side of the stop produces an immediate degraded state.

---

# Phase D, deterministic risk constitution

## D1. Complete policy validation

**Files:**

- Create: `src/policy/semantic.py`
- Modify: `src/agentic_engine.py`
- Create: `tests/test_semantic_policy.py`

Validate:

- symbol allowlist
- product type exact match `SUSDT-FUTURES`
- side and action
- entry distance from current mark
- SL/TP geometry
- expiry
- spread
- slippage
- funding cost
- fee viability
- leverage
- minimum notional
- maximum notional
- daily loss
- drawdown
- maximum concurrent positions
- duplicate symbol exposure
- existing protection state
- reconciliation state
- provider circuit state
- kill switch state

Every rejection must have a stable machine-readable code.

## D2. Add effective-risk report

**Files:**

- Modify: `src/policy/sizing.py`
- Create: `src/policy/risk_report.py`
- Create: `tests/test_risk_report.py`

Report:

```text
requested risk
actual quantity
actual notional
actual stop distance
actual realized risk
risk as percent of equity
risk versus daily loss cap
leverage implied by margin
minimum-notional distortion
```

The system must refuse to call configured risk “realized risk” when venue floors or caps change the result.

## D3. Circuit breakers

**Files:**

- Create: `src/policy/breakers.py`
- Create: `tests/test_breakers.py`

Breakers:

```text
provider breaker
market data breaker
rate-limit breaker
reconciliation breaker
protection breaker
daily loss breaker
drawdown breaker
runtime heartbeat breaker
```

All breakers park new entries. Only the operator-side process or a verified automatic recovery may clear them. The model cannot clear any breaker.

### Acceptance gate D

- Every unsafe proposal is rejected before execution.
- Risk report reflects actual venue constraints.
- Any breaker parks entries deterministically.
- Breaker state persists across restart.
- No provider response can modify policy or breakers.

---

# Phase E, read-only UI projection from the trust spine

## E1. Add `/api/state` projection

**Files:**

- Modify: `scripts/ui_server.py`
- Create: `tests/test_ui_state_api.py`

The endpoint must expose only ledger and approved read-only demo venue facts:

```json
{
  "mode": "demo-readonly",
  "writable": false,
  "product_type": "SUSDT-FUTURES",
  "kill_switch": true,
  "provider": "healthy|degraded|parked",
  "market_data": "fresh|stale|unknown",
  "reconciliation": "sync|drift|unknown",
  "protection": "protected|degraded|unknown|idle",
  "latest_cycle": {},
  "disposition_counts": {},
  "open_positions": [],
  "recent_events": []
}
```

The endpoint must not expose secrets and must not make order or transfer calls.

## E2. Replace all fixture claims

**Files:**

- Modify: `ui/index.html`
- Create: `tests/test_ui_projection.py`

Remove or label all fixture-only values. Display:

- `No paper cycle recorded` when ledger is empty.
- `No open position` when venue and ledger agree.
- `Protection unknown` rather than `idle` when it has not been measured.
- `Read-only / no execution` as the primary capability state.
- Timestamp freshness and last successful read.
- Source labels: `ledger`, `demo venue`, `fixture`, or `unavailable`.

No button may imply that a browser-only action changes runtime state.

## E3. Add evidence drawer

The UI should include a compact expandable evidence panel for the latest cycle:

```text
cycle ID
context hash
decision status
policy disposition
order ID
fill ID
fee
protection evidence
reconciliation evidence
terminal disposition
```

No raw provider secret, private key, or sensitive header may be rendered.

## E4. Browser QA

Run real Chromium at:

```text
360x800
390x844
768x844
1024x900
1440x900
```

Acceptance:

- no horizontal document overflow
- no clipped text
- tables become mobile cards
- no console errors
- all displayed timestamps Asia/Jakarta
- read-only boundary visible above the fold
- no sticky header
- gutters symmetric
- desktop density remains readable

### Acceptance gate E

- Fresh browser load and server restart show the same ledger state.
- UI state changes after a paper cycle without hard-coded fixture activity.
- `POST`, `PUT`, and `DELETE` return `405`.
- UI cannot clear kill switch or create any state-changing venue call.
- Browser verification passes all required sizes.

---

# Phase F, autonomous demo operation

## F1. Add one-command paper runtime

**Files:**

- Create: `scripts/run_autonomous_paper.py`
- Create: `tests/test_autonomous_paper_cli.py`

Command behavior:

```bash
python3 scripts/run_autonomous_paper.py \
  --mode paper \
  --cycles 100 \
  --symbols BTCUSDT ETHUSDT
```

Default behavior:

- fake exchange only
- no network
- no credentials
- no live product
- bounded cycle count
- durable SQLite ledger
- graceful shutdown
- terminal summary

## F2. Add read-only demo shadow operation

**Files:**

- Create: `scripts/run_autonomous_shadow.py`
- Create: `tests/test_autonomous_shadow_cli.py`

This mode may read public demo tickers and the demo account balance. It must not call signed order endpoints. It must produce decisions and dispositions in the local ledger without execution.

## F3. Add demo execution as an explicit separate mode

**Files:**

- Create: `src/execution/bitget_demo.py`
- Create: `tests/test_bitget_demo_adapter.py`
- Modify: `docs/DEMO_ONLY.md`

Hard locks:

- only `SUSDT-FUTURES` or the verified Bitget demo-coin mode
- no `USDT-FUTURES` production mode
- no transfer endpoint
- no withdrawal endpoint
- no leverage mutation unless explicitly encoded in policy
- no order without `DEMO_EXECUTION_CONFIRM=1`
- every order gets an idempotent client ID
- every order must be read back
- every fill must be read back
- every position must be reconciled
- protection must be verified or the runtime parks and closes according to emergency policy

Do not use ad hoc scripts as the runtime execution architecture.

## F4. Demo run acceptance

Only run the demo runtime after gates A through E pass.

Initial constraints:

```text
one symbol
max_concurrent=1
minimum measured quantity
no transfer permission
no withdrawal permission
no public deployment
bounded cycle count
automatic close on protection failure
```

Required report:

```text
cycles
provider outcomes
policy outcomes
orders
fills
fees
protection status
reconciliation status
terminal dispositions
remaining positions
```

If any position remains open, stop and reconcile before ending the run.

---

# Phase G, self-review and adaptation loop

## G1. Automatic review artifacts

After every bounded run, generate:

```text
reports/run-<id>.json
reports/run-<id>.md
```

The report must contain:

- raw counts from ledger
- all rejection codes
- all degraded states
- provider latency and failure rate
- duplicate prevention results
- protection evidence
- reconciliation evidence
- fee-inclusive paper outcome
- unresolved anomalies

## G2. Independent review pass

Run three isolated review functions after each implementation milestone:

1. safety and execution review
2. data integrity and ledger review
3. UI truthfulness and responsive review

A review may block the next phase. Do not suppress negative findings.

## G3. Change gate

A new strategy, provider, prompt, or policy version must pass:

- fixture replay
- paper suite
- schema suite
- policy suite
- protection suite
- reconciliation suite
- browser projection suite

No strategy change may directly enable live or demo execution.

## G4. Rollback

Rollback automatically to:

```text
PARKED
```

when:

- provider error threshold is breached
- market data is stale
- ledger integrity fails
- protection is degraded
- reconciliation drifts
- runtime heartbeat expires
- duplicate order risk is detected

Rollback preserves all events and never deletes evidence.

---

# Phase H, deployment hygiene

## H1. Standalone service only

Create a separate service definition only after the offline runtime is stable:

```text
northline-agentic-demo.service
```

It must:

- use `/root/bitget-agentic-architecture`
- run under a dedicated user if possible
- load only the standalone `.env`
- expose only localhost by default
- start in `shadow` or `paper`
- require an explicit demo execution gate
- never share the live bot service

## H2. Provenance

Before each milestone:

```bash
git status --short --ignored
git diff --check
python3 -m compileall -q src scripts
python3 -m pytest -q
```

Commit only tracked non-secret files. Confirm:

```bash
git check-ignore .env
```

## H3. Public UI deployment

Do not deploy publicly until:

- read-only claims are accurate
- authentication is added for sensitive state
- state-changing methods remain disabled
- HTTPS is configured
- no credentials are exposed
- browser QA passes the public URL

---

# Final acceptance criteria

The phase is complete only when all are true:

1. A bounded autonomous paper run can start, resume, and finish without user input.
2. Every cycle has exactly one durable terminal disposition.
3. Duplicate snapshots do not duplicate provider calls or orders after restart.
4. Provider failure never produces an order.
5. Policy failure never produces an order.
6. Kill switch and breakers park entries independently of the provider.
7. Protection is evidence-based and persisted.
8. Missing protection produces degraded state and entry parking.
9. Reconciliation runs before new entries after restart.
10. Ledger replay reproduces the runtime state.
11. Read-only UI projects ledger truth and demo venue truth.
12. UI contains no fake “enabled”, “protected”, “profitable”, or “live” claims.
13. No endpoint can transfer, withdraw, or access production product type.
14. `SUSDT-FUTURES` is the only accepted demo product in standalone execution.
15. `/opt/bots/bitget-listener` is unchanged.
16. All tests pass with zero warnings.
17. Real Chromium verifies all required responsive viewports.
18. Every report includes negative findings and unresolved risks.
19. No profit or performance claim is made without fee-inclusive ledger evidence.
20. The system can autonomously run normal cycles, but cannot autonomously weaken its own constitution.

## Recommended execution order

```text
A -> B -> C -> D -> E -> F -> G -> H
```

Do not skip directly from the current scaffold to demo execution. The highest-value work is the durable trust spine and protection supervisor, not additional model complexity.
