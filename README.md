# Bitget Fully Agentic Trading Architecture

`Status: architecture scaffold, not connected to live funds`

This directory describes a fully autonomous trading system in which an AI provider is the strategy agent. There is no trader signal source and no human approval per trade.

The agent may propose trades and the system may execute them automatically, but deterministic policy code remains the authority for risk, permissions, sizing, execution validity, and emergency shutdown. This is not a profit guarantee.

## Integration boundary

This directory is standalone and is intentionally separate from `/opt/bots/bitget-listener`. It does not import, modify, restart, or deploy the existing live bot. See `docs/INTEGRATION_BOUNDARY.md`.

## Current implementation status

The standalone implementation now includes provider abstraction, strict decision parsing, normalized market snapshots, read-only public market adapter, autonomous runner, deterministic sizing, durable kill switch, fake exchange, append-only ledger, reconciliation, protection verification, restart recovery, shadow runner, and a testnet safety gate. It has not placed an order or made a signed exchange call.

## Operating modes

- `shadow`: ingest market data, generate decisions, validate them, record what would have happened, place zero orders.
- `paper`: send decisions through the complete execution path against a fake exchange adapter.
- `testnet`: use the venue test environment with hard-coded safe limits.
- `live`: real Bitget orders. This mode must be enabled outside application defaults and only after the gates in `docs/ROLLOUT.md` pass.

## Core invariant

```text
LLM can suggest an action.
Policy engine can reject it.
LLM cannot alter policy, permissions, ledger, or kill switch.
Execution submits only a policy-approved order.
```

## Directory map

```text
config.example.yaml       Safe example configuration
contracts/                JSON contracts for agent decisions and execution intents
docs/ARCHITECTURE.md      Production topology and data flow
docs/THREAT_MODEL.md      Threats, controls, residual risks
docs/ROLLOUT.md           Shadow -> paper -> testnet -> live gates
docs/OPERATIONS.md        Runtime operations and observability
schemas/                  JSON Schema definitions
src/agentic_engine.py     Dependency-free decision/policy scaffold
tests/test_engine.py      Offline invariant tests
architecture.html         Standalone visual architecture diagram
```

## Important boundary

This is intentionally separate from `/opt/bots/bitget-listener`. It does not import that bot, read its `.env`, modify its service, or place an order. Integration should be an explicit later phase.

## Provider abstraction

The production adapter should support Anthropic API, OpenAI-compatible APIs, or a local model through the same interface. A Claude Max web subscription is not treated as a production API dependency. Provider failure means `NO_DECISION`, never an invented trade.

## Autonomous does not mean unconstrained

No human is required to approve each trade. The machine still enforces:

- symbol and venue allowlists
- maximum notional and leverage
- maximum daily loss and drawdown
- stale-data and spread checks
- maximum order frequency
- mandatory protection plan
- idempotency
- circuit breaker and kill switch
- append-only audit trail

These controls are the autonomous system's constitution. Removing them would not make the bot more agentic. It would make it unsafe and untestable.
