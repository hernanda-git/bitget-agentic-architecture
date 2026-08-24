# Fully Agentic Trading System, Next Implementation Plan

**Target directory:** `/root/bitget-agentic-architecture`

**Goal:** Build an autonomous AI trading engine that replaces the trader signal entirely. The agent observes normalized Bitget market data, generates structured decisions, and executes automatically without per-trade human approval.

**Non-goal:** Do not modify, restart, deploy, or connect to `/opt/bots/bitget-listener` during this plan. Integration with the existing live bot is a later, separately approved migration.

## Operating doctrine

```text
The AI is autonomous for normal enter/manage/exit decisions.
The AI is never the authority for secrets, policy, withdrawals, or kill-switch state.
Provider failure means HOLD or PARK, never a guessed order.
Venue read-back, not local optimism, defines fills, protection, and balance.
```

## Phase 0, freeze the boundary

### Task 0.1, record repository boundary

Files:

- Modify: `README.md`
- Create: `docs/INTEGRATION_BOUNDARY.md`

Document that this directory is standalone, has no live credentials, and cannot import the existing Bitget bot as a runtime dependency. Add a test that scans source for forbidden imports and live paths.

Verification:

```bash
cd /root/bitget-agentic-architecture
python3 -m pytest -q
```

Expected: all tests pass and no test imports `/opt/bots/bitget-listener`.

### Task 0.2, establish immutable safe defaults

Files:

- Modify: `config.example.yaml`
- Create: `src/config.py`
- Create: `tests/test_config.py`

Implement typed config loading with fail-closed behavior:

- default mode `shadow`
- `dry_run=true`
- `testnet=true`
- `kill_switch=true`
- `withdrawals_enabled=false`
- no credential defaults
- reject `live` if an explicit deployment gate file is absent

Do not allow the LLM to load or mutate configuration.

## Phase 1, provider-neutral agent boundary

### Task 1.1, define provider interface

Files:

- Create: `src/providers/ports.py`
- Create: `src/providers/fake.py`
- Create: `tests/test_provider_boundary.py`

Define an async interface such as:

```python
class AgentProvider(Protocol):
    async def decide(self, context: AgentContext) -> ProviderResponse: ...
```

The provider receives structured context only. It receives no exchange adapter and no signing object.

### Task 1.2, add Anthropic adapter

Files:

- Create: `src/providers/anthropic.py`
- Create: `tests/test_anthropic_adapter.py`

Use the Anthropic API, not browser automation and not a Claude Max web subscription. Add:

- timeout
- one bounded retry
- response size cap
- provider circuit breaker
- model and prompt version fields
- no secret logging
- malformed response -> `NO_DECISION`

The provider adapter must be replaceable by OpenAI-compatible or local providers without changing policy or execution code.

### Task 1.3, build strict decision parser

Files:

- Modify: `schemas/agent-decision.schema.json`
- Create: `src/decision_parser.py`
- Create: `tests/test_decision_parser.py`

Reject:

- unknown keys if strict mode is enabled
- missing decision id
- invalid action
- invalid symbol format
- nonnumeric levels
- oversized thesis or response
- expiry missing or already expired

Never repair an invalid model response into a valid trade. Return `NO_DECISION`.

## Phase 2, real market-data subsystem, read-only first

### Task 2.1, define normalized market models

Files:

- Create: `src/market/models.py`
- Create: `tests/test_market_models.py`

Models must include:

- symbol
- mark price
- bid and ask
- candle windows
- funding rate
- open interest when available
- observed timestamp
- source timestamp
- snapshot hash
- freshness status

Reject impossible values and timestamp regressions.

### Task 2.2, implement Bitget public adapter

Files:

- Create: `src/market/bitget_public.py`
- Create: `tests/test_bitget_public.py`

Read-only endpoints first. Enforce:

- request throttling
- timeout and retry policy
- 429 backoff
- circuit breaker
- response schema validation
- no private endpoints
- no order methods

Test with recorded fixtures. Do not use live credentials.

### Task 2.3, build snapshot store and freshness gate

Files:

- Create: `src/market/snapshot_store.py`
- Create: `src/market/freshness.py`
- Create: `tests/test_freshness.py`

A stale or inconsistent snapshot must produce `PARKED_MARKET_DATA`. No model call is necessary when the input is invalid.

## Phase 3, context and autonomous decision loop

### Task 3.1, build bounded context

Files:

- Create: `src/agent/context.py`
- Create: `tests/test_context.py`

Context includes market snapshot, current venue positions, open orders, recent ledger events, exposure, fees, funding, and prior agent decisions. It excludes secrets and arbitrary external text instructions.

Hash the exact context sent to the provider.

### Task 3.2, build one-cycle orchestrator

Files:

- Create: `src/agent/cycle.py`
- Create: `tests/test_cycle.py`

One cycle must:

1. Load fresh snapshot.
2. Build bounded context.
3. Call provider once.
4. Parse strict JSON.
5. Run policy validation.
6. Produce a terminal disposition.
7. Persist the trace.

Provider failure, timeout, malformed JSON, or empty response must be terminal and safe.

### Task 3.3, add cadence and concurrency control

Files:

- Create: `src/agent/runner.py`
- Create: `tests/test_runner.py`

Prevent overlapping cycles for the same symbol. Add a maximum cycle frequency and idempotent cycle IDs. A process restart must not duplicate an existing intent.

## Phase 4, deterministic policy and risk engine

### Task 4.1, expand semantic policy validation

Files:

- Modify: `src/agentic_engine.py`
- Create: `src/policy/semantic.py`
- Create: `tests/test_policy_semantic.py`

Validate:

- allowlisted symbol
- live mark price and spread
- entry distance from mark
- correct long/short SL and TP geometry
- decision expiry
- leverage cap
- notional cap
- maximum concurrent positions
- daily loss and drawdown
- funding and fee constraints
- duplicate position restrictions

All returns must use explicit rejection codes.

### Task 4.2, implement deterministic sizing

Files:

- Create: `src/policy/sizing.py`
- Create: `tests/test_sizing.py`

The model may propose a maximum notional, but final quantity is calculated by deterministic code. It must use real venue specifications and reject when the minimum notional makes intended risk impossible.

Report effective realized risk, not merely configured risk.

### Task 4.3, implement autonomous kill switch

Files:

- Create: `src/policy/kill_switch.py`
- Create: `tests/test_kill_switch.py`

Kill switch behavior:

- refuse new entries immediately
- keep reconciliation alive
- keep protection monitoring alive
- cannot be cleared by the model
- persist state durably

## Phase 5, paper execution and accounting

### Task 5.1, fake exchange adapter

Files:

- Create: `src/execution/ports.py`
- Create: `src/execution/fake_exchange.py`
- Create: `tests/test_fake_exchange.py`

Support deterministic simulation of:

- order acknowledgement
- partial fills
- fees
- funding
- rejected orders
- missing protection
- stale position state
- duplicate client order ID

### Task 5.2, append-only ledger

Files:

- Create: `src/ledger/events.py`
- Create: `src/ledger/sqlite.py`
- Create: `tests/test_ledger.py`

Persist the full trace from market snapshot to final disposition. Store raw provider response hash, model, prompt version, policy version, intent, order, fill, fee, protection, and reconciliation result.

### Task 5.3, paper runner

Files:

- Create: `scripts/run_paper.py`
- Create: `tests/test_paper_e2e.py`

Run the complete loop with zero venue side effects. The final report must show:

- decision count
- approval/rejection count by reason
- simulated orders
- fills
- net PnL after fees
- protection failures
- reconciliation drift

## Phase 6, reconciliation and protection

### Task 6.1, venue read-back interface

Files:

- Create: `src/reconcile/ports.py`
- Create: `src/reconcile/engine.py`
- Create: `tests/test_reconciliation.py`

The exchange remains source of truth for:

- balance
- positions
- open orders
- fills
- fees
- liquidation price
- protection

Local state drift must park new entries.

### Task 6.2, protection verifier

Files:

- Create: `src/execution/protection.py`
- Create: `tests/test_protection.py`

A position is not healthy until protection is read back and matches the intended levels. If venue protection is unavailable, use a separately tested bot-side monitor and mark the position `DEGRADED`, never `PROTECTED`.

### Task 6.3, restart recovery

Files:

- Create: `tests/test_restart_recovery.py`

Simulate restart with:

- open position
- open order
- partial fill
- missing ledger event
- provider outage
- active kill switch

Recovery must reconcile before allowing new entries.

## Phase 7, shadow evaluation

### Task 7.1, real public-data shadow runner

Files:

- Create: `scripts/run_shadow.py`
- Modify: `docs/ROLLOUT.md`

Use real public Bitget data with zero signed calls and zero orders. Run at least 7 days or 1,000 cycles.

Measure:

- provider latency
- provider error rate
- schema rejection rate
- policy rejection rate
- HOLD rate
- decision flat-line behavior
- simulated expectancy after fees
- data freshness

Do not use model confidence as proof of edge.

## Phase 8, testnet and micro-live adapter

### Task 8.1, signed Bitget adapter

Files:

- Create: `src/execution/bitget.py`
- Create: `tests/test_bitget_execution.py`

Implement only typed operations needed by the policy. Do not implement withdrawal. Add idempotency, rate limiting, venue read-back, and fail-closed error handling.

### Task 8.2, testnet gate

Files:

- Create: `scripts/run_testnet.py`
- Create: `tests/test_testnet_gate.py`

Require explicit testnet configuration and reject production product type. Test order, fill, protection, reconciliation, restart, and kill switch.

### Task 8.3, micro-live gate

Only after all previous gates pass:

- one allowlisted symbol initially
- `max_concurrent=1`
- smallest practical notional
- explicit external deployment action
- no per-trade human approval
- live balance and venue state verified before first entry
- rollback plan ready

Do not connect this architecture to the existing Bitget service automatically.

## Final acceptance criteria

The system is ready for a separately approved integration only when:

- All unit and end-to-end paper tests pass.
- Shadow evidence covers the required cycle count.
- No provider failure can create an order.
- No LLM response can mutate policy or access secrets.
- Every order is idempotent and read back from Bitget.
- Every position has verified protection or a clearly marked degraded fallback.
- Reconciliation parks on drift.
- Kill switch works independently of the model.
- Ledger is complete enough to reconstruct every decision.
- Live mode cannot be enabled through a model response or normal agent tool.
- No profit or win-rate claim is made without real, fee-inclusive evidence.
