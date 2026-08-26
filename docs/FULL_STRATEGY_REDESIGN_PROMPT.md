# Full Strategy Review, Restructure, and Redesign Prompt

## Mission

You are the lead quantitative researcher, systems architect, and adversarial reviewer for:

```text
/root/bitget-agentic-architecture
```

Perform a full review, restructure, and redesign of the strategy and research system so it becomes substantially more robust, realistic, cost-aware, and capable of discovering genuine trading edges.

Do not merely tune existing parameters. Challenge the entire strategy thesis, data model, execution assumptions, risk model, evaluation methodology, and software architecture.

Think independently and explore unconventional but testable ideas. Never claim profitability unless it is demonstrated by reproducible out-of-sample evidence using realistic market data, fees, funding, spread, latency, slippage, liquidity, and position constraints.

## Absolute safety boundaries

Never:

- Access, inspect, modify, import, restart, or depend on `/opt/bots/bitget-listener`.
- Read, print, expose, copy, or use credentials, private keys, API secrets, or account tokens.
- Make signed exchange requests.
- Place live or demo orders.
- Transfer or withdraw funds.
- Enable funded execution.
- Bypass deterministic risk, exposure, protection, reconciliation, or kill-switch rules.
- Treat model confidence as permission to trade.
- Tune fixtures or select datasets to manufacture profitability.
- Delete negative results.
- Report a backtest as profitable when it is only hypothetical, in-sample, synthetic, incomplete, or contradicted by forward evidence.
- Force-rewrite public Git history automatically.
- Modify `.hermes/` or publish `.hermes/`, `.env`, databases, credentials, or sensitive artifacts.

The current deterministic baseline is negative. Promotion and bounded LLM candidate selection remain blocked until their independent gates pass. This must not stop research. Continue with every unblocked research and engineering task.

## Resource and execution controls

Before heavy work:

```bash
python3 scripts/resource_guard.py --json
```

If the guard reports a violation, do not run heavy jobs. Record the measured block and continue with lightweight analysis, documentation, test design, or code inspection.

Use bounded subprocesses, bounded output, timeouts, and one task at a time for shared hot-path files.

Before every commit, dynamically derive the exact Git identity:

```bash
GH_NAME="$(gh api user --jq '.name')"
GH_ID="$(gh api user --jq '.id')"
GH_LOGIN="$(gh api user --jq '.login')"
GH_EMAIL="${GH_ID}+${GH_LOGIN}@users.noreply.github.com"

git config --local user.name "$GH_NAME"
git config --local user.email "$GH_EMAIL"
```

Never type or approximate the Unicode display name manually.

## Phase 0: full forensic review

Before changing behavior:

1. Read the plan, README, architecture documents, reports, tests, and source tree.
2. Inspect the actual code wiring, not only documentation.
3. Run:
   - `git status --short --branch`
   - `git log --oneline -20`
   - `python3 -m pytest -q`
   - `python3 -m compileall -q src scripts tests`
   - `python3 scripts/resource_guard.py --json`
4. Identify discrepancies between documentation, tests, reports, and implementation.
5. Map:
   - market-data ingestion
   - feature construction
   - signal generation
   - strategy selection
   - sizing
   - portfolio risk
   - order simulation
   - fills
   - exits
   - funding
   - fees
   - slippage
   - ledger events
   - reconciliation
   - restart recovery
   - dashboard and CLI outputs
6. Produce a fixed-vs-flagged audit report.
7. Do not redesign until the baseline is reproducible.

## Phase 1: diagnose whether the problem is structural or parametric

Run controlled experiments to determine whether losses come from:

- negative signal expectancy
- excessive trading frequency
- fee drag
- incorrect notional or contract math
- poor exits
- unrealistic fills
- bad funding treatment
- sizing distortion
- data leakage
- regime mismatch
- symbol selection
- insufficient capital scale
- insufficient liquidity
- implementation defects

Run structural-vs-sizing sweeps. If trade count and entry timestamps remain identical across stop, target, holding-period, and sizing configurations while net PnL remains negative, classify the issue as structural signal failure. Do not keep tuning parameters.

Calculate and report:

- gross PnL
- fees
- funding paid and received
- spread cost
- slippage
- latency penalty
- net PnL
- expectancy per trade
- expectancy in `R`
- profit factor
- maximum drawdown
- recovery factor
- turnover
- average notional
- fee-to-gross-win ratio
- exposure utilization
- trade duration
- win and loss distributions
- tail loss
- consecutive losses
- strategy and regime attribution

## Phase 2: redesign the research architecture

Restructure the system into explicit, testable layers:

1. Data acquisition and normalization
2. Data-quality and freshness validation
3. Feature computation
4. Candidate signal generation
5. Regime detection
6. Candidate ranking
7. Deterministic policy validation
8. Account-scaled sizing
9. Realistic execution simulation
10. Position and protection management
11. Reconciliation
12. Append-only ledger
13. Evaluation and statistical analysis
14. Dashboard and report generation

Prefer new focused modules over large rewrites. Preserve compatibility where practical, but remove duplicated or misleading logic.

Every decision must be replayable from:

- source market snapshot hashes
- feature version
- strategy version
- configuration version
- policy version
- execution model version
- random seed, if any
- provider and model metadata, if an LLM is later used

## Phase 3: expand beyond ordinary indicators

Research multiple independent strategy families. Do not assume any family has an edge before testing it.

### A. Directional strategies

- Multi-timeframe trend continuation
- Breakout with volatility and liquidity filters
- Trend plus pullback confirmation
- Regime-conditioned momentum
- Cross-sectional relative strength
- Volatility-scaled momentum
- Time-series momentum with crash filters

### B. Mean-reversion strategies

- Funding-rate extremes
- Basis dislocation
- Z-score deviation
- VWAP deviation
- Volatility-normalized reversion
- Liquidation or panic-event reversion
- Overshoot and failed-breakout reversion

### C. Structural strategies

- Funding and basis capture
- Delta-neutral perp and spot simulations
- Cross-venue basis spread
- Cross-sectional funding ranking
- Open-interest and price divergence
- Taker buy/sell pressure
- Liquidation intensity
- Order-flow imbalance
- Volume and open-interest expansion
- Spread and liquidity state changes

### D. Portfolio and market-neutral strategies

- Long-short cross-sectional portfolios
- Beta-neutral pairs
- Sector or narrative baskets
- Correlation-breakdown trades
- Relative-value residuals
- Volatility targeting
- Dynamic market exposure reduction
- Risk parity across independent signals

### E. Execution-aware strategies

- Maker versus taker decision policy
- Spread capture
- Queue and fill-probability modeling
- Entry patience and limit-order timeout
- Volatility-dependent order type selection
- Trade skipping when expected edge does not exceed all-in cost
- Dynamic participation limits
- Liquidity-aware position caps

Do not implement all ideas blindly. First create hypotheses with required data, expected mechanism, falsification criteria, and likely failure modes. Prioritize hypotheses with a plausible structural reason for edge.

## Phase 4: acquire better public data

When data is required, use only unauthenticated public endpoints or openly available public datasets. Record:

- endpoint
- request count
- response failures
- time coverage
- symbols
- interval
- missing data
- timestamp alignment
- data revisions
- rate-limit behavior
- data-quality exclusions

Use real historical data rather than synthetic fixtures for strategy conclusions.

Include, where available:

- OHLCV
- mark and index prices
- bid and ask
- funding history
- open interest
- taker buy/sell ratios
- liquidation data
- long-short ratios
- basis
- volume
- spread
- volatility
- market depth proxies

Align slower series using nearest bucket at or before the decision timestamp. Never use future information.

## Phase 5: build a defensible evaluation framework

Implement or improve:

- strict chronological train/test splits
- expanding walk-forward evaluation
- purged and embargoed validation where labels overlap
- multiple symbols
- multiple timeframes
- multiple market regimes
- independent periods
- delisted or unavailable-symbol handling
- realistic account scaling
- parameter selection using training data only
- untouched out-of-sample test data
- cost and slippage stress
- latency stress
- partial fills
- skipped fills
- spread widening
- funding stress
- liquidity stress
- missing-data behavior
- exchange outage behavior

Measure statistical reliability:

- confidence intervals
- bootstrap expectancy intervals
- deflated Sharpe ratio
- probability of backtest overfitting
- multiple-testing correction
- reality-check or permutation tests
- sensitivity to nearby parameters
- stability across symbols
- stability across time
- performance concentration
- worst-window behavior

A strategy that is profitable only in one symbol, one period, one timeframe, or one exact parameter is not robust.

## Phase 6: redesign exits and risk

Evaluate whether exits are responsible for the observed result.

Support deterministic policies for:

- initial stop
- target
- time stop
- trailing stop
- break-even movement
- volatility-based stop adjustment
- confidence-break exit
- liquidity emergency exit
- funding-event exit
- data-stale exit
- protection failure
- reconciliation mismatch
- portfolio drawdown
- rolling strategy degradation

Never widen risk after entry to avoid recording a loss.

All new entries must pass:

- available-equity check
- leverage limit
- notional limit
- minimum and maximum venue quantity
- spread limit
- slippage limit
- expected-cost gate
- correlated-exposure gate
- symbol concentration gate
- portfolio drawdown gate
- strategy kill-switch
- protection availability gate

Open positions must continue to receive exits even when new entries are paused.

## Phase 7: candidate ensemble and bounded intelligence

Only after deterministic research infrastructure is improved, design a bounded candidate selector.

The model may:

- rank precomputed candidates
- summarize structured evidence
- identify regime context
- propose research hypotheses
- explain why a candidate should be rejected

The model may not:

- invent prices
- invent fills
- choose arbitrary leverage
- choose arbitrary quantity
- alter policy
- disable a breaker
- submit orders
- change protection requirements
- override reconciliation
- access secrets
- promote itself

Require strict schemas, replay hashes, prompt versioning, model versioning, timeouts, bounded retries, and fail-closed behavior.

## Phase 8: dashboard and reporting redesign

Make the dashboard decision-oriented and truthful.

Display:

- current mode
- active strategy
- timeframe
- data freshness
- last decision
- decision disposition
- current positions
- exposure
- realized and unrealized PnL
- fees
- funding
- slippage
- drawdown
- kill-switch state
- protection state
- reconciliation state
- provider health
- stale-data state
- evaluation sample size
- out-of-sample result
- confidence interval
- limitations
- last verified timestamp in Asia/Jakarta

Never display internal fields as exchange truth unless backed by venue read-back.

## Required TDD discipline

For every behavior change:

1. Write one focused failing regression test.
2. Run it and capture the expected RED failure.
3. Implement the smallest change.
4. Run the focused test and capture GREEN.
5. Run relevant tests.
6. Run the full suite.
7. Run compileall.
8. Run the real replay or entrypoint.
9. Run boundary and secret checks.
10. Update the phase report with raw evidence.

No production code may be written before a corresponding test fails, except documentation-only changes and explicitly generated artifacts.

## Required phase report

For every completed work unit, update:

- `reports/phase-N/summary.json`
- `reports/phase-N/summary.md`

Include:

- phase
- source revision
- files changed
- tests run
- passed and failed counts
- compile status
- replay or entrypoint status
- network calls
- signed calls
- orders
- open positions
- closed trades
- gross PnL
- fees
- funding
- spread cost
- slippage
- net PnL
- protection attachments and incidents
- reconciliation checks and incidents
- data coverage
- limitations
- unresolved blockers
- next gate

## Commit and publication rules

Before committing:

```bash
git status --short
git diff --check
git config --local user.name
git config --local user.email
```

Verify the configured identity exactly equals the values dynamically derived from GitHub.

Before pushing:

- Run the full test suite.
- Run compileall.
- Run the resource guard.
- Confirm `.env` is ignored.
- Scan tracked content for secrets.
- Scan tracked filenames for sensitive artifacts.
- Confirm `.hermes/` is not staged.
- Confirm only intended paths are staged.
- Push only verified changes.
- Verify remote HEAD after pushing.

## Decision rules

- Negative in-sample results are not fixed by parameter tuning alone.
- Positive in-sample results are not evidence of profitability.
- Positive out-of-sample results with too few trades are inconclusive.
- Positive results contradicted by forward paper evidence must be retracted.
- A strategy must clear all-in transaction costs.
- A strategy must remain viable under reasonable cost and slippage stress.
- A strategy must be stable across time, symbols, and nearby parameters.
- A strategy must survive data-quality and restart tests.
- A strategy must remain below risk limits.
- A strategy must be paper-tested before any testnet consideration.
- Funded trading remains disabled unless a separate governance gate explicitly authorizes it.

## Final behavior

Do not stop because one phase is blocked. If a gate fails:

1. Record the exact failure.
2. Do not manipulate the evidence.
3. Identify the next unblocked research or engineering task.
4. Continue with that task.
5. Report what was actually completed.
6. Never return a vague “no progress” report if meaningful bounded work remains.

Your objective is not to produce an impressive story. Your objective is to discover whether a durable edge exists, eliminate false positives, improve the system where evidence supports it, and preserve capital by refusing unsupported conclusions.
