# Bitget Agentic Architecture

## Full high-level architecture and end-to-end flow

**Repository:** `hernanda-git/bitget-agentic-architecture`
**Runtime modes:** `shadow`, `paper`, `testnet`, and a separately gated `live` design
**Current operational posture:** offline paper and public-data research only
**Funded execution:** disabled
**Timezone for displayed timestamps:** `Asia/Jakarta`
**Canonical timestamps:** stored in machine-readable form for replay and audit

> This document explains how the system is designed to run, what is implemented, what is measurement-only, and which gates prevent unsafe execution. It is an architecture and operating guide, not a profitability claim.

---

## 1. The central idea

The system is an autonomous decision pipeline, not an unrestricted AI trader.

```text
Market data is observed.
Features and strategies produce candidates.
An agent may analyze or rank bounded candidates.
Deterministic policy decides what is allowed.
Sizing calculates the actual quantity.
Execution uses typed intents.
Protection and reconciliation verify state.
The ledger records the entire trace.
```

The authority order is:

1. Venue and market-data truth
2. Deterministic safety policy
3. Deterministic sizing and portfolio risk
4. Execution and protection verification
5. Bounded model proposal or ranking
6. Human governance at deployment and funding boundaries

The model is never the source of truth for price, balance, fill, position, fee, liquidation price, or protection state.

---

## 2. System context

```mermaid
flowchart LR
    subgraph External[External world]
        PUB[Public market data\nREST / WebSocket]
        VENUE[Venue truth\norders / fills / positions / fees]
        CLOCK[Host clock and OS resources]
    end

    subgraph System[Bitget Agentic Architecture]
        INGEST[Market Data Gateway]
        NORMALIZE[Snapshot Normalizer]
        FEATURES[Feature Builder]
        STRATEGIES[Strategy Research Engine]
        CONTEXT[Bounded Context Builder]
        MODEL[Provider Adapter\noptional bounded LLM]
        PARSER[Decision Schema + Semantic Validator]
        POLICY[Deterministic Policy Engine]
        SIZE[Deterministic Sizing + Portfolio Risk]
        INTENT[Typed Execution Intent]
        PAPER[FakeExchange / Paper Execution]
        EXEC[Venue Execution Adapter\nfuture gated path]
        PROTECT[Protection Supervisor]
        RECON[Reconciliation]
        BREAKERS[Breaker Registry\nkill switch / resource / heartbeat]
        LEDGER[(Append-only SQLite Ledger)]
        EVAL[Walk-forward Evaluation\nstatistics / stress]
        UI[Read-only Dashboard + CLI]
        SCHED[Scheduler / Runtime Supervisor]
    end

    PUB --> INGEST
    INGEST --> NORMALIZE
    NORMALIZE --> FEATURES
    FEATURES --> STRATEGIES
    NORMALIZE --> CONTEXT
    FEATURES --> CONTEXT
    STRATEGIES --> CONTEXT
    CONTEXT --> MODEL
    MODEL --> PARSER
    STRATEGIES --> PARSER
    PARSER --> POLICY
    BREAKERS --> POLICY
    POLICY --> SIZE
    SIZE --> INTENT
    INTENT --> PAPER
    INTENT -. future, separately gated .-> EXEC
    PAPER --> PROTECT
    EXEC -. future .-> PROTECT
    PROTECT --> RECON
    VENUE -. read-back only .-> RECON
    RECON --> BREAKERS
    CLOCK --> BREAKERS
    SCHED --> INGEST
    SCHED --> BREAKERS
    SCHED --> RECON
    NORMALIZE --> LEDGER
    CONTEXT --> LEDGER
    PARSER --> LEDGER
    POLICY --> LEDGER
    INTENT --> LEDGER
    PAPER --> LEDGER
    PROTECT --> LEDGER
    RECON --> LEDGER
    BREAKERS --> LEDGER
    LEDGER --> UI
    LEDGER --> EVAL
```

### Component responsibilities

| Component | Responsibility | Authority | Current status |
|---|---|---|---|
| Market Data Gateway | Fetches public observations and validates transport, schema, timestamps, and freshness | External data is untrusted input | Implemented for public shadow |
| Snapshot Normalizer | Converts venue payloads to stable internal snapshots | Normalization only | Implemented |
| Feature Builder | Computes versioned features from snapshots | Deterministic | Implemented |
| Strategy Research Engine | Generates candidate signals and regime labels | Proposes candidates only | Implemented and expanding |
| Context Builder | Creates bounded structured context | Cannot include secrets | Implemented conceptually and in runtime paths |
| Provider Adapter | Abstracts the selected inference provider | No execution authority | Provider-pinned cron configuration |
| Decision Validator | Checks JSON shape and semantic validity | Rejects malformed output | Implemented |
| Policy Engine | Enforces hard rules | Final entry permission | Implemented |
| Sizing and Risk | Calculates actual quantity and portfolio impact | Overrides provider quantity | Implemented |
| Execution Intent | Typed, idempotent proposed action | No direct signing | Implemented for paper |
| FakeExchange | Simulates fills, fees, funding, spread, slippage, stops, targets | Deterministic paper authority | Implemented |
| Venue Adapter | Future authenticated exchange adapter | Must be separately gated | Not active |
| Protection Supervisor | Ensures stop and target state | Safety authority | Paper coverage implemented |
| Reconciliation | Compares external state with local state | Venue read-back authority | Paper and design coverage |
| Breaker Registry | Parks new entries under unsafe conditions | Deterministic only | Resource and heartbeat breakers wired |
| Ledger | Stores immutable runtime evidence | Audit authority | Implemented with SQLite |
| Evaluator | Measures out-of-sample behavior and costs | Promotion evidence only | Implemented and expanding |
| Dashboard | Read-only projection of measured state | No execution authority | Implemented and browser-verified |
| Scheduler | Drives periodic observations and monitors | Operational orchestration | Cron configured, gateway dependent |

---

## 3. Operating modes

```mermaid
stateDiagram-v2
    [*] --> SHADOW
    SHADOW: Public data, zero orders
    SHADOW --> PAPER: Data and schema gates pass
    PAPER: FakeExchange, full simulated lifecycle
    PAPER --> TESTNET: Governance gate + testnet credentials
    TESTNET: Venue sandbox only
    TESTNET --> MICRO_LIVE: Separate approval and evidence gate
    MICRO_LIVE: Smallest live capital, hard caps
    MICRO_LIVE --> SCALE: Forward evidence passes
    SCALE: Controlled increase only

    SHADOW --> PAUSED: Data degraded or breaker open
    PAPER --> PAUSED: Resource / policy / integrity failure
    TESTNET --> PAUSED: Reconciliation or protection failure
    MICRO_LIVE --> PAUSED: Loss, drift, or protection failure
    PAUSED --> SHADOW: Explicit recovery and clean verification
```

### `shadow`

- Uses public unauthenticated data only.
- Produces observations, features, decisions, and hypothetical dispositions.
- Places zero orders.
- Does not use exchange signing credentials.

### `paper`

- Uses the complete decision and execution path.
- Sends typed intents to `FakeExchange`.
- Models fills, partial fills, fees, funding, spread, slippage, stops, targets, and end-of-replay closure.
- Produces actual paper ledger records.

### `testnet`

- Future venue sandbox mode.
- Requires separate credentials and explicit testnet configuration.
- Must prove order, fill, protection, and reconciliation read-back.
- Must not reuse funded credentials.

### `live`

- Designed but disabled by default.
- Requires all governance, statistical, operational, protection, reconciliation, and forward-evidence gates.
- No current code path is authorized to activate funded trading automatically.

---

## 4. Market-data flow

```mermaid
sequenceDiagram
    autonumber
    participant S as Scheduler
    participant G as Public Data Gateway
    participant V as Public Venue API
    participant Q as Quality Validator
    participant N as Snapshot Normalizer
    participant L as Ledger
    participant F as Feature Builder

    S->>G: Request next observation
    G->>V: Unauthenticated public request
    V-->>G: Ticker, candles, funding, OI, volume, metadata
    G->>Q: Validate HTTP, schema, timestamps, freshness
    alt Invalid, stale, regressing, or incomplete data
        Q-->>G: Reject fail-closed
        G->>L: Record DATA_DEGRADED / rejection
        G-->>S: HOLD or PARK disposition
    else Valid observation
        Q->>N: Accept payload
        N->>N: Normalize prices, candles, timestamps, symbol
        N->>N: Compute deterministic snapshot hash
        N->>L: Record MARKET_OBSERVED
        N->>F: Build versioned features
        F->>L: Record feature version and source hash
        F-->>S: Structured observation ready
    end
```

### Data-quality rules

The gateway must fail closed on:

- Missing required fields
- Non-positive prices
- Bid greater than ask
- Invalid symbols or products
- Timestamp regression
- Future-dated observations
- Stale snapshots
- Incomplete candle windows
- Chronologically reordered candles
- Mixed-symbol replay inputs
- Missing or inconsistent snapshot hashes
- Rate limits, provider outages, and malformed responses

A mark price does not have to lie inside the quoted bid and ask. It must be positive, while bid and ask must be positive and ordered.

Slow data series are joined using the nearest bucket at or before the decision timestamp. Future values are never used.

---

## 5. One runtime decision cycle

```mermaid
flowchart TD
    START([Cycle starts]) --> RESOURCE[Read resource and breaker state]
    RESOURCE -->|Unsafe / breaker open| PARK[Park new entries]
    RESOURCE -->|Healthy| OBSERVE[Load fresh market snapshot]
    OBSERVE --> QUALITY{Data valid and fresh?}
    QUALITY -->|No| HOLD1[HOLD / DATA_DEGRADED]
    QUALITY -->|Yes| BUILD[Build features and regime]
    BUILD --> CONTEXT[Build bounded context]
    CONTEXT --> CANDIDATES[Generate deterministic candidates]
    CANDIDATES --> MODELQ{Bounded model needed?}
    MODELQ -->|No| DECIDE[Use deterministic candidate path]
    MODELQ -->|Yes| CALL[Call pinned provider with timeout]
    CALL --> RESPONSE{Response received?}
    RESPONSE -->|No| HOLD2[HOLD / PROVIDER_FAILURE]
    RESPONSE -->|Yes| PARSE[Parse strict decision schema]
    PARSE --> SEMANTIC{Semantic checks pass?}
    SEMANTIC -->|No| REJECT1[REJECT / SCHEMA_OR_SEMANTIC_FAILURE]
    SEMANTIC -->|Yes| DECIDE
    DECIDE --> POLICY{Deterministic policy passes?}
    POLICY -->|No| REJECT2[REJECT / POLICY_GATE]
    POLICY -->|Yes| SIZE[Calculate deterministic size]
    SIZE --> RISK{Sizing and portfolio risk pass?}
    RISK -->|No| REJECT3[REJECT / RISK_GATE]
    RISK -->|Yes| INTENT[Create idempotent execution intent]
    INTENT --> EXECUTE[Submit to FakeExchange]
    EXECUTE --> FILL{Fill observed?}
    FILL -->|No| FAILED[ORDER_FAILED / no position]
    FILL -->|Yes| PROTECT[Attach and verify stop/target]
    PROTECT --> PROTECTED{Protection verified?}
    PROTECTED -->|No| PARK2[PARK entries / protection failure]
    PROTECTED -->|Yes| RECON[Reconcile local state]
    RECON --> FINAL[Persist terminal disposition]
    PARK --> FINAL
    HOLD1 --> FINAL
    HOLD2 --> FINAL
    REJECT1 --> FINAL
    REJECT2 --> FINAL
    REJECT3 --> FINAL
    FAILED --> FINAL
    PARK2 --> FINAL
    FINAL --> END([Cycle complete])
```

Every cycle ends in a terminal disposition:

```text
EXECUTED
REJECTED
HELD
PARKED
FAILED
```

There are no silent cycles and no implicit success states.

---

## 6. Strategy and research flow

```mermaid
flowchart LR
    DATA[Historical and public snapshots] --> CLEAN[Quality and chronology checks]
    CLEAN --> SPLIT[Chronological train / test split]
    SPLIT --> WF[Expanding walk-forward windows]
    WF --> FAM[Candidate families]

    FAM --> DIR[Directional\ntrend / breakout / momentum]
    FAM --> MR[Mean reversion\nz-score / funding extremes]
    FAM --> RV[Relative value\npairs / basis / residuals]
    FAM --> FLOW[Order flow\ntaker / OI / liquidation]
    FAM --> NEUTRAL[Market neutral\nfunding / basis / beta neutral]
    FAM --> EXEC[Execution-aware\nspread / maker / fill probability]

    DIR --> COST[All-in cost model]
    MR --> COST
    RV --> COST
    FLOW --> COST
    NEUTRAL --> COST
    EXEC --> COST

    COST --> STRESS[Fee / funding / spread / slippage / latency stress]
    STRESS --> STATS[Bootstrap / PF / expectancy / drawdown / DSR]
    STATS --> MULTI[Multiple-testing correction]
    MULTI --> ATTRIB[Strategy / regime / symbol attribution]
    ATTRIB --> OOS[Out-of-sample evidence]
    OOS --> GATE{Robust and adequate evidence?}
    GATE -->|No| RESEARCH[Reject, park, or create new hypothesis]
    GATE -->|Yes| PAPER[Paper observation gate]
```

### Candidate families

The research engine can evaluate:

- Multi-timeframe trend continuation
- Volatility breakouts
- Pullback and failed-breakout logic
- Funding-rate mean reversion
- Basis dislocation
- VWAP and z-score reversion
- Open-interest and price divergence
- Taker-flow pressure
- Liquidation-event response
- Cross-sectional momentum
- Pairs and residual relative value
- Delta-neutral funding capture simulations
- Liquidity-aware execution
- Maker versus taker decision logic

A candidate is not enabled merely because it has a high backtest return. It must pass data, statistical, cost, stability, and forward-evidence checks.

---

## 7. Walk-forward evaluation flow

```mermaid
sequenceDiagram
    autonumber
    participant D as Dataset
    participant V as Input Validator
    participant T as Training Window
    participant E as Evaluation Window
    participant X as Execution Model
    participant C as Cost Stress
    participant A as Attribution
    participant R as Report Validator

    D->>V: Load snapshots and candle windows
    V->>V: Check hashes, symbols, timestamps, chronology
    V-->>D: Reject malformed or future-leaking inputs
    D->>T: Provide only historical training segment
    T->>T: Select candidate/config using training data
    T->>E: Freeze selected configuration
    E->>X: Replay unseen test segment
    X->>X: Model fills, partial fills, exits, protection
    X->>C: Apply fees, funding, spread, slippage, latency
    C->>A: Produce per-trade and per-regime results
    A->>A: Bootstrap and robustness calculations
    A->>A: Multiple-testing correction and DSR
    A->>R: Assemble evidence report
    R->>R: Reject unsupported winner or promotion claims
    R-->>R: Emit honest report with limitations
```

### Evaluation invariants

- Training data cannot select parameters using future test data.
- Incomplete trailing windows are excluded.
- Reordered candles are rejected.
- Costs are charged exactly once.
- Funding received offsets funding paid.
- Slippage is included in net PnL.
- Spread and execution slippage remain separately attributable.
- Results are reported per strategy, symbol, timeframe, regime, and window.
- Positive results with inadequate samples remain inconclusive.
- A single favorable window cannot establish a durable edge.

---

## 8. Deterministic sizing and portfolio risk

```mermaid
flowchart TD
    CANDIDATE[Approved candidate] --> ACCOUNT[Account snapshot]
    ACCOUNT --> EQUITY[Equity and available margin]
    ACCOUNT --> EXPOSURE[Gross, net, symbol, correlated exposure]
    CANDIDATE --> STOP[Entry and stop distance]
    STOP --> RISK[Requested risk budget]
    RISK --> RAW[Raw risk-based quantity]
    RAW --> VENUE[Tick, step, min, max, notional, leverage rules]
    VENUE --> CAP[Account and exposure caps]
    EXPOSURE --> CAP
    EQUITY --> CAP
    CAP --> EFFECTIVE[Effective quantity and effective risk]
    EFFECTIVE --> GATE{All sizing gates pass?}
    GATE -->|No| REJECT[Reject entry]
    GATE -->|Yes| INTENT[Create typed intent]
```

The provider cannot determine the final quantity. The deterministic sizing layer applies:

- Requested risk
- Stop distance
- Contract multiplier
- Venue quantity step
- Minimum and maximum notional
- Leverage cap
- Available equity
- Gross exposure
- Net exposure
- Correlated exposure
- Symbol concentration
- Drawdown and loss limits

Minimum-notional distortion is reported rather than hidden.

---

## 9. Paper execution lifecycle

```mermaid
stateDiagram-v2
    [*] --> NEW_INTENT
    NEW_INTENT: Typed idempotent intent
    NEW_INTENT --> REJECTED: Invalid or duplicate
    NEW_INTENT --> NEW_ORDER: Accepted by FakeExchange
    NEW_ORDER --> PARTIAL: Partial fill
    NEW_ORDER --> FILLED: Full fill
    NEW_ORDER --> EXPIRED: No fill before expiry
    PARTIAL --> PARTIAL: More fill
    PARTIAL --> FILLED: Remaining fill
    PARTIAL --> CANCELLED: Cancel remainder
    FILLED --> PROTECTION_PENDING
    PROTECTION_PENDING --> PROTECTION_VERIFIED: Stop and target attached
    PROTECTION_PENDING --> PROTECTION_FAILED: Missing or invalid protection
    PROTECTION_FAILED --> PARKED: New entries disabled
    PROTECTION_VERIFIED --> OPEN
    OPEN --> STOP_EXIT: Stop triggered
    OPEN --> TARGET_EXIT: Target triggered
    OPEN --> REDUCE_EXIT: Reduce-only exit
    OPEN --> END_REPLAY_EXIT: Replay ends
    STOP_EXIT --> CLOSED
    TARGET_EXIT --> CLOSED
    REDUCE_EXIT --> CLOSED
    END_REPLAY_EXIT --> CLOSED
    CLOSED --> RECONCILED
    RECONCILED --> [*]
    PARKED --> [*]
    REJECTED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
```

The paper exchange models:

- Market and limit orders
- Partial and complete fills
- Duplicate intent rejection
- Quantity and price constraints
- Bid and ask execution
- Adverse slippage
- Spread cost
- Fees
- Funding paid or received
- Reduce-only exits
- Stop and target protection
- Gap-through-stop behavior
- End-of-replay flattening
- Closed-trade accounting

The replay cannot finish with an unexplained open position. Any residual paper position receives a typed `END_OF_REPLAY` close using the final executable side.

---

## 10. Protection and reconciliation flow

```mermaid
flowchart TD
    POSITION[Position opened] --> ATTACH[Create protection intent]
    ATTACH --> VERIFY[Verify stop and target]
    VERIFY --> POK{Protection valid?}
    POK -->|No| PFAIL[Protection failure]
    PFAIL --> PARK[Park new entries]
    PFAIL --> EMERGENCY[Follow deterministic emergency-exit policy]
    POK -->|Yes| MONITOR[Monitor position and mark progression]
    MONITOR --> EXIT{Exit condition?}
    EXIT -->|Stop| STOP[Reduce-only stop exit]
    EXIT -->|Target| TARGET[Reduce-only target exit]
    EXIT -->|Time / confidence / liquidity| RULE[Deterministic rule exit]
    EXIT -->|No| RECON[Periodic reconciliation]
    STOP --> RECON
    TARGET --> RECON
    RULE --> RECON
    RECON --> MATCH{Local and venue state match?}
    MATCH -->|No| DRIFT[Reconciliation drift]
    DRIFT --> PARK2[Park new entries and alert]
    DRIFT --> RECOVER[Repair or explicit recovery path]
    MATCH -->|Yes| CONTINUE[Continue protected monitoring]
```

Protection rules:

- Existing positions continue to receive exit handling when new entries are parked.
- A missing stop or target is not treated as healthy.
- An order ID or HTTP success is not proof of a fill or resting protection order.
- Venue read-back is required for authenticated execution modes.
- Reconciliation happens after restart before new entries.
- A protection or reconciliation failure parks new entries.

---

## 11. Breakers and resource safety

```mermaid
flowchart TD
    HOST[Host resources] --> RM[ResourceMonitor]
    HEART[Runtime heartbeat] --> HM[HeartbeatMonitor]
    PROVIDER[Provider health] --> PM[Provider circuit]
    OPERATOR[Operator kill switch] --> BR[BreakerRegistry]
    RM --> BR
    HM --> BR
    PM --> BR
    BR --> OPEN{Any breaker open?}
    OPEN -->|No| ALLOW[Entry path may continue]
    OPEN -->|Yes| PARK[Park NEW entries]
    PARK --> EXISTING[Existing positions unchanged]
    EXISTING --> PROTECT[Protection continues]
    EXISTING --> RECON[Reconciliation continues]
    RM -->|Clean verified sample| AUTO[Monitor auto-recovery]
    AUTO --> BR
    OPERATOR -->|Manual trip| BR
    BR --> LEDGER[Record breaker reason and transition]
```

The resource breaker is separate from the preflight resource guard:

| Control | Purpose | Failure behavior |
|---|---|---|
| `scripts/resource_guard.py` | Protects heavy evaluation processes | Blocks or aborts heavy work when limits are exceeded |
| `ResourceMonitor` | Protects runtime entry path | Trips `resource` breaker and parks new entries |
| `BreakerRegistry` | Shared deterministic breaker state | Prevents entry when any required breaker is open |
| Protection supervisor | Protects existing positions | Continues exits and protection verification |
| Reconciliation | Detects local versus external drift | Parks entries and requires recovery |

The model cannot open or clear the resource breaker.

---

## 12. Full ledger and evidence flow

```mermaid
flowchart LR
    CYCLE[Cycle ID and trace ID] --> EVENTS[Canonical runtime events]
    MARKET[Market observation] --> EVENTS
    CTX[Context hash] --> EVENTS
    DEC[Decision and response hash] --> EVENTS
    POL[Policy disposition] --> EVENTS
    ORD[Order and fill records] --> EVENTS
    PROT[Protection evidence] --> EVENTS
    REC[Reconciliation evidence] --> EVENTS
    BREAK[Breaker transitions] --> EVENTS
    EVENTS --> HASH[Canonical payload hash]
    HASH --> SQLITE[(SQLite WAL ledger)]
    SQLITE --> PROJ[Projections]
    PROJ --> STATUS[Runtime state]
    PROJ --> TRADES[Trades and PnL]
    PROJ --> RISK[Positions and exposure]
    PROJ --> EVIDENCE[Evidence rollups]
    STATUS --> UI[Read-only dashboard]
    TRADES --> REPORT[Phase reports]
    RISK --> REPORT
    EVIDENCE --> REPORT
```

Important ledger properties:

- Append-only event records
- Canonical payload hashing
- Schema versions
- Cycle and trace identity
- Foreign keys
- SQLite WAL mode
- Transactional event and projection updates
- Rollback behavior under injected failures
- Durable snapshots
- Restart-safe projections
- Unknown-event rejection
- Bounded payload sizes

Typical event categories include:

```text
MARKET_OBSERVED
FEATURES_BUILT
AGENT_CONTEXT_BUILT
AGENT_DECISION
DECISION_REJECTED
POLICY_REJECTED
INTENT_APPROVED
ORDER_SUBMITTED
ORDER_ACKNOWLEDGED
FILL_OBSERVED
PROTECTION_ATTACHED
PROTECTION_VERIFIED
PROTECTION_FAILED
POSITION_RECONCILED
EXIT_OBSERVED
BREAKER_TRIPPED
BREAKER_RECOVERED
CYCLE_TERMINAL
```

Every decision stores enough metadata to replay it:

- Source snapshot hash
- Feature version
- Strategy version
- Configuration version
- Policy version
- Execution-model version
- Provider and model metadata, if applicable
- Prompt version, if applicable
- Raw response hash, if applicable
- Final disposition

---

## 13. Scheduler and continuous runtime flow

```mermaid
flowchart TD
    SERVICE[Hermes gateway / runtime supervisor] --> CRON[Durable cron scheduler]
    CRON --> WATCH[Resource watchdog every 10m]
    CRON --> WORKER[Autonomous phase worker every 60m]
    CRON --> HEALTH[Runtime heartbeat and health checks]
    WATCH --> ALERT[Pressure alert or silent healthy result]
    WATCH --> GUARD[Resource guard state]
    GUARD --> WORKER
    WORKER --> PREFLIGHT[Repository and resource preflight]
    PREFLIGHT --> PHASE[Select next unblocked phase]
    PHASE --> TDD[TDD RED -> GREEN -> REFACTOR]
    TDD --> VERIFY[Full test, compile, replay, scan]
    VERIFY --> REPORT[Phase report]
    REPORT --> COMMIT[Commit with exact GitHub identity]
    COMMIT --> PUSH[Secret scan and push]
    PUSH --> DELIVERY[Telegram run report]
```

### Scheduler reality

Cron definitions can exist while the Hermes gateway is stopped. In that state:

- Jobs are saved.
- Jobs may show as enabled.
- Future scheduled ticks do not fire.
- Manual runs may still be possible through the control interface.
- The gateway must be running for continuous unattended scheduling.

This distinction is operationally important. A configured job is not the same as a currently executing job.

---

## 14. Autonomous phase-worker flow

```mermaid
flowchart TD
    TRIGGER[Scheduled or manual trigger] --> IDENTITY[Derive Git identity from gh api]
    IDENTITY --> STATUS[Read git status and current revision]
    STATUS --> GUARD[Run resource guard]
    GUARD -->|Violation| LIGHT[Document block and do lightweight work]
    GUARD -->|Healthy| PLAN[Read current plan and phase reports]
    PLAN --> GATE{Current phase gate open?}
    GATE -->|No| BLOCK[Record blocker]
    BLOCK --> NEXT[Choose next unblocked engineering task]
    GATE -->|Yes| TASK[Implement one bounded work unit]
    NEXT --> TASK
    TASK --> RED[Write failing test]
    RED --> GREEN[Minimal implementation]
    GREEN --> FOCUSED[Focused tests]
    FOCUSED --> FULL[Full suite and compileall]
    FULL --> RUNTIME[Replay or real entrypoint verification]
    RUNTIME --> REPORT[Update phase report]
    REPORT --> SCAN[Secret and boundary scans]
    SCAN --> COMMIT[Commit exact intended paths]
    COMMIT --> REMOTE[Push and verify remote]
    REMOTE --> DELIVERY[Report actual evidence]
    LIGHT --> DELIVERY
```

The worker must not stop merely because a promotion gate is negative. It should continue with unblocked work such as:

- Data-quality validation
- Cost-model improvements
- Walk-forward statistics
- Strategy attribution
- Protection and reconciliation
- Runtime health
- Resource safety
- Dashboard truthfulness
- Public-data research
- Documentation and reproducibility

---

## 15. Bounded model flow

```mermaid
sequenceDiagram
    autonumber
    participant B as Context Builder
    participant P as Pinned Provider
    participant S as Schema Validator
    participant R as Risk and Policy Engine
    participant X as Execution Path
    participant L as Ledger

    B->>P: Bounded structured context
    P-->>B: JSON candidate or analysis
    B->>S: Candidate response
    S->>S: Validate schema and semantic fields
    alt Invalid, stale, or malformed
        S->>L: DECISION_REJECTED
        S-->>X: No intent
    else Valid candidate
        S->>R: Normalized proposal
        R->>R: Apply deterministic venue and portfolio policy
        alt Policy rejects
            R->>L: POLICY_REJECTED
            R-->>X: No intent
        else Policy approves
            R->>X: Typed intent with deterministic quantity
            X->>L: INTENT_APPROVED
        end
    end
```

The model may:

- Rank precomputed candidates
- Summarize structured evidence
- Explain regime context
- Suggest research hypotheses
- Recommend rejection

The model may not:

- Invent prices or fills
- Choose arbitrary quantity or leverage
- Change stop or protection policy
- Disable breakers
- Alter allowlists
- Change risk limits
- Sign requests
- Submit orders directly
- Access secrets
- Promote a strategy

The current deterministic negative baseline keeps bounded LLM selection blocked for promotion purposes.

---

## 16. Promotion gate flow

```mermaid
flowchart TD
    BASE[Reproducible deterministic baseline] --> DATA[Real sufficient data coverage]
    DATA --> OOS[Chronological out-of-sample evidence]
    OOS --> COST[Net after fees, funding, spread, slippage, latency]
    COST --> STABLE[Stability across symbols, time, regimes, nearby parameters]
    STABLE --> STATS[Statistical robustness and multiple-testing controls]
    STATS --> FORWARD[Paper forward evidence]
    FORWARD --> OPS[Protection, reconciliation, restart, and failure tests]
    OPS --> TESTNET[Testnet read-back gate]
    TESTNET --> GOVERN[Governance approval]
    GOVERN --> MICRO[Micro-live gate, if separately authorized]
    MICRO --> SCALE[Controlled scaling]

    BASE -->|Negative or inconclusive| NO[Remain blocked and research]
    DATA -->|Insufficient| NO
    OOS -->|Negative| NO
    COST -->|Negative| NO
    STABLE -->|Unstable| NO
    STATS -->|Insufficient| NO
    FORWARD -->|Contradicts backtest| NO
    OPS -->|Failure| NO
```

Promotion is blocked if any of the following occurs:

- Negative net PnL
- Inadequate trade count
- No independent out-of-sample period
- Cost-inclusive expectancy is not positive
- Results depend on one symbol or one exact parameter
- Forward paper evidence contradicts replay
- Protection cannot be proven
- Reconciliation cannot be proven
- Restart recovery fails
- Data quality is insufficient
- Resource safety is not operational
- Report evidence is incomplete or contradictory

User authorization does not replace statistical or safety evidence.

---

## 17. Current implementation reality

### Implemented and verified

- Append-only validated ledger
- SQLite WAL and transactional projections
- Deterministic paper exchange
- Fees, funding, spread, and slippage accounting
- End-of-replay flattening
- Deterministic sizing
- Portfolio exposure gates
- Public-data adapter and data-quality validation
- Versioned features
- Strategy and regime attribution
- Walk-forward evaluation
- Cost stress testing
- Multiple-testing and Deflated Sharpe measurement
- Report truthfulness guard
- Read-only dashboard projection
- Browser-responsive dashboard verification
- Heartbeat breaker
- Resource breaker
- Entry parking when breakers are open
- Resource-pressure end-to-end test
- Resource watchdog
- Bounded heavy-work resource guard
- Safe GitHub publication workflow

### Measurement-only or limited

- Public historical-data research is not funded execution.
- Synthetic adverse fixtures are not live profitability evidence.
- Paper protection is not authenticated venue protection.
- Paper reconciliation is not exchange reconciliation.
- The current runtime monitor still needs a permanent timer loop in the long-running service for continuous resource and heartbeat sampling.
- The dashboard has been verified primarily with empty-state data; populated-cycle density requires additional browser evidence.
- Phase 6 bounded LLM selection remains blocked by the negative deterministic baseline.

---

## 18. Current known findings

The deterministic baseline remains negative after realistic accounting.

Representative evidence includes:

```text
Promotion: blocked
Reason: NEGATIVE_NET_PNL
```

The system has intentionally become more conservative as accounting improved. Fees, funding, spread, and slippage are not hidden.

The correct engineering response is:

- Improve data coverage.
- Test structurally different hypotheses.
- Distinguish dead signals from sizing defects.
- Reduce fee bleed and overtrading.
- Test market-neutral and structural mechanisms.
- Preserve negative findings.
- Require independent forward evidence.

The incorrect response is to tune parameters until a report looks positive.

---

## 19. Operational runbook

### Run the baseline

```bash
python3 scripts/run_strategy_baseline.py \
  --output reports/phase-5/baseline.json
```

### Run the resource guard

```bash
python3 scripts/resource_guard.py --json
```

### Run all tests

```bash
python3 -m pytest -q
```

### Compile-check the project

```bash
python3 -m compileall -q src scripts tests
```

### Inspect repository state

```bash
git status --short --branch
git log -10 --oneline
```

### Inspect cron state

```bash
hermes cron list
hermes cron status
```

### Start the Hermes gateway for durable scheduling

```bash
hermes gateway status
hermes gateway start
```

Only start the gateway after checking the current process topology and resource condition. Starting the gateway is separate from enabling funded trading. It does not authorize exchange orders.

---

## 20. Summary in one diagram

```mermaid
flowchart TB
    subgraph Observe[1. Observe]
        O1[Public data]
        O2[Host resources]
        O3[Clock / heartbeat]
    end

    subgraph Understand[2. Understand]
        U1[Normalize snapshots]
        U2[Build features]
        U3[Classify regimes]
        U4[Generate candidates]
        U5[Build bounded context]
    end

    subgraph Decide[3. Decide]
        D1[Optional bounded model]
        D2[Strict schema validation]
        D3[Deterministic policy]
        D4[Deterministic sizing]
        D5[Portfolio risk]
    end

    subgraph Act[4. Act safely]
        A1[Typed intent]
        A2[FakeExchange paper fill]
        A3[Protection]
        A4[Reconciliation]
        A5[Breaker handling]
    end

    subgraph Prove[5. Prove]
        P1[Append-only ledger]
        P2[Replay]
        P3[Walk-forward]
        P4[Cost stress]
        P5[Truthful reports]
        P6[Dashboard]
    end

    Observe --> Understand --> Decide --> Act --> Prove
    O2 --> A5
    O3 --> A5
    A5 --> Decide
    P2 --> Decide
    P3 --> Decide
```

The complete system is therefore a closed evidence loop:

```text
Observe -> validate -> understand -> propose -> constrain -> size -> execute
-> protect -> reconcile -> record -> evaluate -> improve -> repeat
```

No stage is allowed to silently bypass the next stage, and no positive result is accepted without reproducible evidence.
