# Full Strategy Review, Restructure, and Redesign

- Review timestamp: `2026-08-26T22:46:22+0700` (`Asia/Jakarta`)
- Repository: `/root/bitget-agentic-architecture`
- Scope: standalone tree only
- Safety boundary: `/opt/bots/bitget-listener` was not accessed, imported, modified, restarted, or used
- External signed calls: `0`
- Orders placed by this review: `0`
- Credentials/private keys printed or used: `0`

## 1. Executive verdict

**BLOCKED for demo and funded execution.** The repository has a substantially implemented offline architecture with strong deterministic authority boundaries, typed ledger contracts, protection state handling, public-history quality gates, and reproducible cost-inclusive evaluation. The strategy evidence remains negative and the runtime composition is not evidence of live-market readiness.

The largest evidence-backed problem is not missing model complexity. It is the absence of demonstrated positive, cost-adjusted, out-of-sample edge. Stored public-history results are negative:

- BTCUSDT 5m, 2,000 candles: `250` closed trades, net PnL `-13,333.8886`, promotion `false`.
- BTCUSDT 5m, 6,000 candles: `353` closed trades, net PnL `-25,223.9833`, promotion `false`.
- BTCUSDT 1m, 1,500 candles: `35` closed trades, net PnL `-5,224.3824`, promotion `false`.
- The 6,000-candle result includes observed funding records and still remains negative.

Therefore, parameter tuning or adding an LLM selector is not justified. Research should continue under a parked promotion gate, prioritizing independent data, better execution realism, and falsifiable strategy hypotheses.

## 2. Evidence collected

### Boundary and resource checks

- `python3 scripts/resource_guard.py --json`: `ok=true`; available memory `1,547,083,776` bytes; swap usage `73.50%`; disk use `43.03%`; inode free `52.70%`; no violations.
- `git status --short --branch`: branch `master`; pre-existing uncommitted changes are limited to `scripts/evaluate_real_history.py`, `src/market/history.py`, `tests/test_funding_readiness_gate.py`, and the untracked redesign prompt.
- `scripts/baseline_check.py --output /tmp/bitget-baseline.json`: boundary `true`, compile `true`, `275` collected tests, no detected secrets.

### Runtime verification

- `python3 -m compileall -q src scripts`: passed.
- `python3 -m pytest --collect-only -q`: `275` collected.
- `python3 -m pytest -q --timeout=20 --timeout-method=thread`: `275 passed in 7.02s`.
- Offline paper enter run, `3` cycles: integrity `true`, `6` paper orders, `3` closed positions, `0` open positions, protection verified `3`, reconciliation `3`, network calls `0`, signed calls `0`, net PnL `1.869`.
- Offline paper hold run, `2` cycles: integrity `true`, `0` orders, `0` open positions, replay terminal dispositions `HELD: 2`.
- Fixture shadow run, `3` cycles: `SHADOW_ONLY`, `0` orders, network calls `0`, signed calls `0`.
- `python3 scripts/replay_ledger.py /tmp/bitget-paper-hold.sqlite3`: replay returned `HELD: 2`, no open positions, reconciliation `UNKNOWN`, risk breaker `CLOSED`.
- Launcher help/status probes passed for the baseline, paper, shadow, replay, and review entrypoints.

The full-suite timeout control initially failed because `pytest-timeout` was not installed. It was installed locally, then the bounded suite completed successfully. This dependency/setup issue is recorded, not hidden.

## 3. Scorecard

Scores are evidence-based and separate architecture quality from profitability.

| Area | Score | Verdict | Evidence |
|---|---:|---|---|
| Architecture | 8/10 | PROVEN | Layered `src/` modules, autonomous paper runtime, public data, policy, ledger, reconciliation, protection, UI projection |
| Runtime reliability | 7/10 | PROVEN with limits | `275` tests, compile clean, bounded paper enter/hold/replay pass |
| Safety and authority boundaries | 7/10 | PROVEN offline | model boundary, kill switch, breakers, demo product allowlist, zero calls in review |
| Execution correctness | 6/10 | PROVEN only in fake exchange | fee/spread/slippage/partial-fill tests pass; no venue execution was exercised |
| Protection | 7/10 | PROVEN offline | supervisor and mark-monitor tests; historical research reports no venue reconciliation |
| Reconciliation | 6/10 | PROVEN offline | fake paper traces reconcile; no live/demo read-back performed |
| Ledger/evaluability | 7/10 | PROVEN with compatibility debt | durable tables, migrations, replay, hashes; legacy append facade remains |
| Market-data realism | 5/10 | PARTIAL | public historical candles and funding exist; historical bid/ask is assumed, not observed |
| Strategy edge evidence | 1/10 | BLOCKED | stored real-history net PnL is negative across the reported datasets |
| Profitability evidence | 1/10 | BLOCKED | no positive robust out-of-sample evidence; synthetic fixture is explicitly non-proof |
| Operational readiness | 4/10 | PARTIAL | offline launcher and reports work; no approved demo/live operation and no service go-live gate |

## 4. Proven strengths

- Deterministic policy remains the authority over model output, sizing, breakers, kill switch, protection, and reconciliation.
- Provider failure and malformed output fail closed.
- The paper path has an explicit terminal disposition and can close an ENTER position before completing.
- Cost accounting separates gross PnL, fees, funding, spread, and execution slippage.
- Real-history evaluation rejects structurally bad data and now rejects inadequate real-funding coverage instead of silently treating missing funding as free.
- Walk-forward and strategy attribution are measurement-only. Selection/promotion remains blocked.
- UI and service tests enforce read-only behavior and reject mutation methods.
- The repository remained standalone during this review. No live bot state was touched.

## 5. Findings

### P1: dangerous signed/demo probe scripts remain in the repository

- **Location:** `scripts/demo_smoke_order.py:10-22`, `scripts/bitget_demo_probe.py:7-23`, `scripts/demo_account_mode_probe.py:11-13`, `scripts/demo_position_probe.py:11-13`.
- **Status:** FLAGGED, not executed.
- **Why:** these ad hoc scripts contain signed-request paths and one uses the production Bitget host. They are outside the offline composition root and are not required for the verified paper workflow. Their presence weakens the absolute boundary in the redesign prompt and makes accidental execution easier.
- **Remediation:** quarantine or remove these scripts from the normal repository surface; if a separately approved demo adapter is retained, expose only typed, allow-listed operations behind an explicit external gate and add a repository-wide test proving the default runtime cannot import or call them.

### P1: fixture shadow and public shadow are separate, easy-to-confuse modes

- **Location:** `scripts/run_autonomous_shadow.py:1-4, 23-26`; `scripts/run_public_shadow.py:23-59`.
- **Status:** FLAGGED.
- **Why:** the default autonomous shadow CLI records fixture observations, while the strategy prompt requires real public data for market conclusions. The reports correctly label the fixture path, but the command naming is easy to misread as public shadow evidence.
- **Remediation:** rename or explicitly label the fixture command as `fixture-shadow`, and make `public-shadow` the only command whose output can be used in market-data reports.

### P1: full lifecycle evidence is split across multiple runtimes

- **Location:** `src/runtime/paper_runtime.py:31-100`; `src/paper_loop.py`; `scripts/run_autonomous_paper.py`.
- **Status:** FLAGGED.
- **Why:** the offline composition works, but the repository has both `AutonomousPaperRuntime` and a separate paper-loop/report path. The review verified each available path, not a single canonical composition root covering every strategy and report feature.
- **Remediation:** designate one canonical runtime and make all CLI/report paths call it. Require one integration replay that proves market observation through terminal state, including ledger projections, protection, reconciliation, and replay equality.

### P2: compatibility ledger APIs permit synthetic legacy identity defaults

- **Location:** `src/ledger/sqlite.py:88-99`; `src/ledger/events.py:16-18`.
- **Status:** FLAGGED.
- **Why:** the compatibility `append()` facade generates a `legacy-*` cycle ID and defaults metadata when callers omit it. This preserves old fixtures, but it weakens the intended rule that every event belongs to an explicit trace and cycle.
- **Remediation:** retain compatibility only behind an explicitly named legacy adapter and reject missing identity in new runtime code. Add migration metrics showing whether legacy events remain.

### P2: historical execution cost assumptions remain incomplete

- **Location:** `src/market/history.py:3-7`; stored real-history reports.
- **Status:** FLAGGED.
- **Why:** historical bid/ask is not available from the selected public endpoint, so spread is represented by an assumed half-spread. This is clearly documented and not a correctness failure, but it limits the strength of the profitability conclusion and could understate adverse execution.
- **Remediation:** acquire public order-book/depth snapshots where legally and operationally practical, or run a range of spread/latency/partial-fill stress scenarios and report the full sensitivity envelope.

## 6. Profitability verdict

**NOT EVIDENCED. Promotion remains blocked.** Negative real-history results are enough to reject promotion, but they are not enough to claim a universal impossibility result. The current conclusion is narrower and defensible: the tested baseline, data windows, cost model, and strategy families did not demonstrate a durable edge.

The next research gate should require all of:

1. independent untouched periods and symbols;
2. chronological walk-forward with purging/embargo where labels overlap;
3. observed or stress-ranged spread, latency, partial fills, and liquidity limits;
4. fee and settlement funding coverage proven in every evaluated window;
5. closed-trade net PnL, expectancy, drawdown, profit factor, and confidence intervals;
6. stability across nearby parameters and regimes;
7. forward public-shadow evidence that is not fixture-derived.

## 7. Redesign architecture

The recommended target is a single trust spine:

```text
public data acquisition
 -> normalization + freshness/data-quality gate
 -> versioned features
 -> independent candidate families
 -> regime annotation
 -> cost/liquidity gate
 -> deterministic policy
 -> deterministic sizing + effective-risk report
 -> simulated execution
 -> position/protection supervisor
 -> reconciliation
 -> append-only event ledger
 -> replay/evaluation
 -> read-only UI projection
```

The bounded model selector remains downstream of deterministic candidate generation and upstream of deterministic policy only. It may rank or explain candidates, but cannot choose quantity, leverage, protection, policy, breakers, credentials, or order methods.

Promotion state should be explicit and durable:

```text
RESEARCH_ONLY -> FIXTURE_SHADOW -> PUBLIC_SHADOW -> PAPER -> DEMO_CANDIDATE -> PARKED
```

Any negative edge, data-quality failure, stale feed, protection gap, reconciliation drift, provider circuit, or resource-pressure violation transitions to `PARKED` for new entries while protection/reconciliation continue.

## 8. TOP 3 blockers before funded execution

1. **No proven strategy edge:** every stored public-history result reviewed here is negative after costs. Do not enable selection or execution based on model confidence.
2. **No venue-backed execution/protection evidence in this workflow:** fake-exchange protection and reconciliation are not proof of demo or live venue behavior. The current repository must remain offline until a separately approved, read-only-first demo gate exists.
3. **Safety surface cleanup:** signed/ad hoc probe scripts and split runtime paths should be quarantined or unified before anyone treats the repository as an execution-ready product.

## 9. Work completed in this review

- Established repository and resource boundaries.
- Ran bounded baseline, compile, collection, full test, paper enter/hold, shadow, replay, launcher, and baseline-report checks.
- Inspected source wiring, lifecycle, ledger, protection, reconciliation, UI/service boundaries, and research reports.
- Preserved the user's pre-existing uncommitted funding-readiness changes.
- Produced this evidence-backed review without making signed calls, orders, credential accesses, or changes to the funded bot.

## 10. Unresolved next gate

Do not start demo execution. First quarantine the signed probe surface, unify the canonical offline composition root, add independent cost/liquidity stress coverage, and rerun the full suite plus public-shadow evaluation with durable Asia/Jakarta reports.
