# Continuation Prompt, Fully Agentic Trading Engine

Copy the entire prompt below into a new Hermes session.

---

You are continuing work on the fully autonomous AI trading architecture at:

```text
/root/bitget-agentic-architecture
```

## User objective

Build a fully agentic crypto trading engine for Bitget. There is no human trader signal source and no manual approval per trade. An AI provider, such as Anthropic, OpenAI-compatible API, or a local model, must observe normalized market data, produce structured trading decisions, and operate the enter/manage/exit loop automatically.

The system must remain production-grade and auditable. Autonomous does not mean unrestricted.

## Hard constraints

1. Do not modify, restart, deploy, or connect to `/opt/bots/bitget-listener` during this task.
2. Do not read or reuse credentials from any other bot directory.
3. Do not ask the user to approve individual trades.
4. Do not give the model private keys, exchange secrets, withdrawal capability, arbitrary HTTP tools, or policy-write access.
5. The model may propose decisions. Deterministic policy code is the authority for symbol, size, leverage, exposure, SL/TP geometry, stale-data checks, idempotency, and kill switch.
6. Provider timeout, quota error, malformed JSON, conflicting market data, or missing protection must result in `HOLD`, `NO_DECISION`, or `PARK`, never an invented order.
7. Exchange read-back is the authority for balance, fills, fees, positions, liquidation price, and protection.
8. Default mode is `shadow`. Default execution is dry-run and testnet. Never make live mode the code default.
9. Never implement withdrawals.
10. Never claim profit, win rate, or live success without raw fee-inclusive evidence.
11. Displayed timestamps must use Asia/Jakarta, UTC+7.
12. Do not use an Anthropic web subscription or browser automation as a production API. Use a provider adapter with explicit API configuration. Claude Max may be useful for development, but it is not the production execution dependency.
13. Do not use an em dash in responses. Use backticks for identifiers and plain punctuation.

## Existing architecture artifacts

Read these files first:

```text
/root/bitget-agentic-architecture/README.md
/root/bitget-agentic-architecture/docs/ARCHITECTURE.md
/root/bitget-agentic-architecture/docs/THREAT_MODEL.md
/root/bitget-agentic-architecture/docs/ROLLOUT.md
/root/bitget-agentic-architecture/docs/OPERATIONS.md
/root/bitget-agentic-architecture/config.example.yaml
/root/bitget-agentic-architecture/schemas/agent-decision.schema.json
/root/bitget-agentic-architecture/src/agentic_engine.py
/root/bitget-agentic-architecture/tests/test_engine.py
```

The current scaffold is intentionally dependency-free and safe. It has a policy boundary and six passing tests. Extend it incrementally, preserving the safe behavior.

## Target production flow

```text
Bitget public market REST/WS
  -> normalized market snapshot
  -> freshness and consistency gate
  -> bounded agent context
  -> provider adapter
  -> strict structured decision
  -> deterministic semantic policy
  -> deterministic sizing and risk policy
  -> idempotent execution intent
  -> Bitget execution adapter
  -> venue order/fill/protection read-back
  -> reconciliation
  -> append-only ledger and metrics
```

The model must not directly call Bitget or sign an order. It returns JSON only. The execution layer accepts typed intents only after policy approval.

## Work order

Implement the next phase from `NEXT_PLAN.md` in small verified increments:

1. Freeze repository boundary and safe config loader.
2. Define provider-neutral interface and fake provider.
3. Add Anthropic provider adapter with timeout, bounded retry, circuit breaker, response limits, and secret redaction.
4. Add strict decision parser and schema enforcement.
5. Add normalized public market-data models and read-only Bitget adapter.
6. Add freshness and consistency gates.
7. Add bounded context builder and one-cycle agent orchestrator.
8. Expand deterministic policy and sizing.
9. Add fake exchange, append-only ledger, and paper end-to-end runner.
10. Add reconciliation and protection verification.
11. Run public-data shadow mode before any signed adapter.
12. Add testnet adapter only after shadow and paper gates pass.
13. Keep micro-live as a separately approved final stage, never automatic.

## Required implementation discipline

For each code task:

1. Read the relevant existing files.
2. Write tests first.
3. Run the focused test and confirm it fails for the expected reason.
4. Implement the minimum code.
5. Run focused tests.
6. Run the full suite.
7. Run secret scan.
8. Inspect `git diff` and `git status`.
9. Commit each logical change with the user identity only if this directory is intentionally made a git repository. Do not touch the live bot repository.

## Required provider contract

The provider boundary should be equivalent to:

```python
async def decide(context: AgentContext) -> ProviderResponse:
    ...
```

The context must include only structured market, portfolio, risk, and recent decision data. It must include provider model and prompt version. It must not include private keys or unrestricted external text instructions.

Provider errors must be represented explicitly:

```text
PROVIDER_TIMEOUT
PROVIDER_UNAVAILABLE
PROVIDER_QUOTA
PROVIDER_MALFORMED
NO_DECISION
```

## Required decision contract

The model may return only:

```text
ENTER
EXIT
REDUCE
HOLD
CANCEL
```

For `ENTER`, require:

- allowlisted symbol
- BUY or SELL side
- positive entry
- positive stop loss
- positive take profit
- valid long or short level geometry
- valid expiry
- leverage within policy
- max notional within policy
- thesis and invalidation text within bounded length

Never silently repair a bad model response into a valid one.

## Required autonomous safety controls

Implement deterministic controls for:

- symbol allowlist
- maximum leverage
- maximum notional
- minimum venue notional
- maximum concurrent positions
- daily loss and drawdown
- stale market data
- spread and slippage
- funding and fee viability
- duplicate decision and client order IDs
- rate limiting and 429 circuit breaker
- protection verification
- venue/local reconciliation drift
- process restart with open position
- independent kill switch

The model must not be able to change these controls.

## Required verification commands

Run from the architecture directory:

```bash
cd /root/bitget-agentic-architecture
python3 -m compileall -q src
python3 -m pytest -q
python3 src/agentic_engine.py
```

Also perform a repository secret scan that detects API keys, private keys, and credentials. Do not print any secret values.

For any network adapter, first use recorded fixtures and fake clients. No live signed calls until the rollout gates in `docs/ROLLOUT.md` are satisfied.

## Required final report

At the end, report:

1. Exact files created or modified.
2. Test command and raw pass count.
3. Compile result.
4. Secret scan result.
5. Whether any network call was made.
6. Whether any order, transfer, or state-changing exchange call was made.
7. Current mode and safe defaults.
8. Remaining blockers.
9. Explicit statement that `/opt/bots/bitget-listener` was not modified.

Do not say “live-ready” unless every acceptance criterion is proven with raw evidence.
