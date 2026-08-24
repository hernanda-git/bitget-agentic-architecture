# Production Architecture

## Objective

Replace the human trader signal with an autonomous market agent. The agent continuously observes market data, forms a thesis, proposes a structured action, and executes automatically when deterministic policy permits it.

## Components

```text
Bitget public REST/WS
  -> Market Data Gateway
  -> Normalized Market Store
  -> Feature Builder
  -> Agent Context Builder
  -> LLM Provider Adapter
  -> Decision Parser + Schema Validator
  -> Deterministic Policy Engine
  -> Execution Intent
  -> Bitget Execution Adapter
  -> Fill/Position Reconciler
  -> Ledger + Event Store
  -> Agent Memory / Performance Evaluator
```

### Market Data Gateway

Reads candles, ticker, order book, funding, open interest, mark price, and liquidation-related public data. It timestamps every observation, rejects malformed payloads, and marks freshness. It never accepts an LLM-generated price as market truth.

### Agent Context Builder

Builds a bounded context window from normalized data. It includes current positions, open orders, recent decisions, realized PnL, fees, and strategy state. It does not include secrets, private keys, or unrestricted tool access.

### Agent Runtime

The LLM receives a fixed system policy and structured context. It returns JSON only. It cannot call arbitrary URLs, edit policy files, change credentials, or directly sign an exchange request.

The agent is allowed to:

- choose among allowlisted symbols
- choose `ENTER`, `EXIT`, `REDUCE`, `HOLD`, or `CANCEL`
- propose limit/market execution within policy
- propose entry, stop, and target levels
- explain thesis and invalidation
- request a rescan after a bounded delay

The agent is not allowed to:

- withdraw funds
- transfer funds
- change leverage limits
- disable protection
- change the kill switch
- add symbols or contracts to an allowlist
- rewrite its own prompt or policy

### Policy Engine

Pure deterministic code. It validates the agent output against live facts and fixed policy. It is fail-closed. A policy rejection produces an auditable `REJECTED` event, not an automatic retry with relaxed rules.

### Execution Adapter

Converts an approved intent to the venue-specific order shape, rate-limits every request, uses idempotency keys, and verifies the venue response and resulting state. An HTTP success without venue read-back is not a fill.

### Reconciler

The exchange is the source of truth for balance, positions, fills, fees, liquidation price, and protection. The reconciler continuously compares venue state against local state. Drift parks new entries and alerts.

### Ledger

Append-only event records:

```text
MARKET_OBSERVED
AGENT_CONTEXT_BUILT
AGENT_DECISION
DECISION_REJECTED
INTENT_APPROVED
ORDER_SUBMITTED
ORDER_ACKNOWLEDGED
FILL_OBSERVED
PROTECTION_VERIFIED
POSITION_RECONCILED
EXIT_OBSERVED
CIRCUIT_BREAKER
KILL_SWITCH
```

Every decision stores the raw market snapshot hash, provider/model, prompt version, response hash, policy version, and final disposition.

## State machine

```text
NO_DECISION
  -> DECISION_PROPOSED
  -> SCHEMA_VALIDATED
  -> POLICY_APPROVED | POLICY_REJECTED
  -> INTENT_SUBMITTED
  -> VENUE_ACKNOWLEDGED
  -> FILL_OBSERVED | ORDER_FAILED
  -> PROTECTION_VERIFIED | PROTECTION_FAILED
  -> POSITION_OPEN
  -> EXIT_PROPOSED
  -> POSITION_CLOSED | RECONCILIATION_REQUIRED
```

No state transition may skip `POLICY_APPROVED`, `FILL_OBSERVED`, or `PROTECTION_VERIFIED`.

## Agent loop

The loop is event-driven, not an uncontrolled infinite prompt loop:

1. Consume a new market snapshot.
2. Reject if data is stale, incomplete, or inconsistent.
3. Build a bounded context.
4. Ask the provider for one structured decision.
5. Validate JSON schema.
6. Validate semantic constraints.
7. Apply risk budget and exposure checks.
8. Submit at most one idempotent intent per cycle.
9. Read back order, fill, position, and protection.
10. Persist the complete trace.
11. Sleep until the next cadence or event.

Provider timeout, quota error, malformed response, conflicting prices, or missing protection always resolves to `HOLD` or `PARK`, never to a guessed trade.

## Multi-agent option

The initial implementation should use one execution authority. If later adding specialized agents, they may be:

- `MarketObserver`: read-only
- `StrategyAnalyst`: proposes thesis
- `RiskReviewer`: deterministic or separately constrained reviewer
- `ExecutionAgent`: submits only approved intents
- `Reconciler`: read-only authority on venue reality

Agents must not share unrestricted wallets or credentials. The execution adapter owns the only venue credential and exposes only typed operations.
