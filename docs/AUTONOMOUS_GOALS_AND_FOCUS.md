# Autonomous Goals and Focus

## Mission

Build a measurable, replayable, safety-gated autonomous trading research system that can determine whether a strategy has a real cost-inclusive edge before any funded execution is considered.

The system is autonomous inside the approved research boundary. It may observe public data, run paper simulations, evaluate candidates, analyze failures, improve code through tests, and publish verified repository changes. It must fail closed at every execution boundary.

## Current state

- Phases 0 through 5 are implemented.
- Full suite is green at the latest verified checkpoint.
- Public shadow uses unauthenticated public data only.
- The deterministic baseline is negative after fees, funding, and slippage.
- Promotion is blocked with `NEGATIVE_NET_PNL`.
- Phase 6 LLM selection is intentionally blocked until the deterministic baseline gate is repaired or honestly re-evaluated.
- Funded trading is disabled.
- The deployed `/opt/bots/bitget-listener` tree is outside this project and must remain untouched.

## Goals

### Goal 1: Preserve a truthful trust spine

Every observation, feature, decision, policy result, order simulation, fill, protection state, reconciliation result, and terminal cycle must be durable, typed, hashable, and replayable.

Success criteria:

- One durable terminal disposition per cycle.
- Replay reproduces runtime outcomes.
- No silent open position, close, protection, or reconciliation state.
- Reports use measured evidence rather than claims.

### Goal 2: Find or falsify a cost-inclusive edge

Use deterministic strategies first. Evaluate trend continuation, mean reversion, volatility breakout, and later structurally different candidates only through recorded data and the same paper path used by runtime.

Success criteria:

- Unseen walk-forward windows.
- Fees, funding, spread, slippage, delays, and partial fills included.
- Closed-trade accounting reconciles to the ledger.
- Negative results remain visible and block promotion.
- No strategy receives credit for an edge already present in another layer.

### Goal 3: Make risk independent of model output

The model may rank or reject existing candidates only after the deterministic candidate and risk layers are proven. Quantity, leverage, stop distance, exposure, and protection policy remain deterministic.

Success criteria:

- Provider cannot invent a symbol, price, quantity, leverage, or protection level.
- Minimum-notional distortion is reported.
- Portfolio and correlation gates are enforced.
- Drawdown and daily-loss state survive restart.

### Goal 4: Improve autonomously without unsafe promotion

Every improvement follows a bounded loop:

```text
observe -> reproduce -> write failing test -> implement smallest fix
-> run focused tests -> run full suite -> replay -> compare metrics
-> inspect diff -> commit -> publish sanitized result
```

A change that worsens the measured baseline is not promoted merely because the code is cleaner. A change that improves backtest results but fails unseen-data, cost, replay, or safety checks is rejected.

### Goal 5: Maintain continuous operational truth

Monitoring must distinguish process health from useful computation.

Track separately:

- process alive
- public market data fresh
- snapshots changing
- features changing
- candidate distribution changing
- provider status
- ledger advancing
- protection fresh
- reconciliation in sync
- breakers active
- entries armed or parked

A service with fresh timestamps but flat decisions is degraded, not healthy.

## Focus order

1. Repair and strengthen the deterministic baseline gate, including explicit handling of the replay-end open position.
2. Add walk-forward splits, unseen-data evaluation, and realistic cost stress.
3. Compare strategy and regime performance without selecting the best result after looking at the test set.
4. Improve candidate quality only when the improvement is supported by reproducible evidence.
5. Implement bounded LLM selection only after deterministic candidates and baseline attribution are ready.
6. Complete protection, emergency-exit, reconciliation, and restart-failure scenarios.
7. Correct the dashboard and CLI so every value has a source and the UI cannot execute signed requests.
8. Build continuous paper/public-shadow runtime and flat-line health checks.
9. Treat demo execution as a separate future gate requiring explicit governance and isolated credentials.
10. Keep funded execution disabled unless every promotion criterion is independently proven and explicitly authorized outside the model.

## Resource safety and self-recovery

- Heavy work must pass `scripts/resource_guard.py` before launch.
- Default hard gates are 768 MiB available RAM, 90% swap use, 85% disk use, 8 GiB free disk, and 10% free inodes.
- Bounded child runs use an explicit timeout and address-space limit.
- The resource watchdog runs every 10 minutes and alerts on pressure.
- The watchdog may remove only stale project-owned temporary artifacts.
- It never kills or restarts Hermes, deployed bots, databases, or unrelated services automatically.
- When pressure is detected, new heavy work is blocked and existing services are left untouched for operator-safe recovery.
- Current evidence shows swap pressure is close to the limit: approximately 84% used. No new large workload should start while this remains elevated.

## Autonomous operating rules

- Automatic execution means offline paper execution or unauthenticated public shadow only.
- No automatic live orders, transfers, withdrawals, key creation, or policy weakening.
- Provider failure, stale data, malformed data, ledger failure, protection uncertainty, reconciliation drift, or breaker state parks new entries.
- Open-position protection and reconciliation continue while new entries are parked.
- No profitability language without closed, cost-inclusive, reproducible evidence.
- No secret values in source, logs, artifacts, commits, reports, or chat.
- No modification or inspection of the deployed bot tree.
- Every phase must produce a report and pass its gate before the next phase starts.
- Publishing is allowed only after a tracked-file secret scan and remote tree verification.

## Definition of success

The system can answer from durable evidence:

1. What data was observed?
2. What features were calculated?
3. What candidates were generated?
4. What did the model select or reject?
5. What deterministic policy ran?
6. What quantity and risk were approved?
7. What simulated or demo venue state actually occurred?
8. What fees, funding, spread, and slippage were charged?
9. Was protection verified?
10. Did local state match venue state?
11. How did the position close?
12. What was net PnL after all costs?
13. Can replay reproduce the result?
14. Does the result survive unseen data and worsened costs?
15. Does the system fail safely when any dependency is unavailable?

Until all answers are supported by evidence, the project remains a research system and not a funded autonomous trader.
