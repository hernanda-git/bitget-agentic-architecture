# Phase 7, research gate and public shadow

## Verdict

`PARKED`. All six bounded public-history evaluations were negative after modeled fees, assumed spread, slippage, and observed funding. No promotion gate can advance the candidate. Negative evidence is preserved in `public-history-runs.json` and the per-run JSON files.

## 7.1 Public-history evaluation

- Source: unauthenticated Bitget public API only.
- Endpoints: `https://api.bitget.com/api/v2/mix/market/candles` and `https://api.bitget.com/api/v2/mix/market/history-fund-rate`.
- Matrix: `BTCUSDT` and `ETHUSDT`, `1m` and `5m`, recent research periods plus an older, pre-designated untouched holdout for each symbol.
- Each run acquired 240 candles and 20 funding records. Each had `funding_missing=0`, zero candle gaps, zero zero-volume bars, zero data-quality failures, and eight walk-forward windows.
- Bounded request evidence: two successful public requests per fetch run, zero failures, zero retries, and zero observed rate limits. No signed calls, credentials, orders, transfers, or withdrawals.
- Aggregate: 114 closed trades and net PnL `-9308.642609406617` across the six runs. Every run returned `promotion_allowed=false`, reason `NEGATIVE_NET_PNL`.

The evaluator now persists endpoint and request metrics in its output payload (`scripts/evaluate_real_history.py:145-161`). Historical bid/ask was not available, so spread remains an explicit assumed half-spread, never an observed quote claim.

## 7.2 Promotion gates

| Gate | Result | Evidence |
|---|---|---|
| Positive net PnL after all modeled costs | `FLAGGED` | All six net PnL values are negative |
| Adequate closed-trade sample | `NOT EVIDENCED` | No minimum threshold is established by the evaluator |
| Positive expectancy with supporting confidence interval | `NOT EVIDENCED` | No confidence-interval gate in these runs |
| Stability across symbols, periods, regimes, parameters | `NOT EVIDENCED` | Six short windows do not establish this claim |
| Cost and latency stress survival | `FLAGGED` | Baseline is already negative; stress matrix is retained per run |
| Data quality and replay integrity | `PROVEN` | All run quality reports passed; chronology and funding checks passed |
| No invalid performance concentration | `NOT EVIDENCED` | No concentration gate was established |
| Forward public-shadow consistency | `NOT EVIDENCED` | No separate forward public-shadow run was needed or claimed |

The failed gates produce `PARKED`, while unblocked research remains possible. No execution mode was enabled.

## 7.3 Independent reviews

### Safety and execution: `FLAGGED`

- `scripts/audit_safety_surface.py --json` returned overall `FLAGGED`, with three findings.
- `src/execution/bitget_demo.py:120` contains the signed-request implementation. It was not invoked.
- The scanner also flags `.env:1` and `data/paper.sqlite3:1` as sensitive filenames.
- The public-history path is separately read-only: `src/market/bitget_public.py:1-4` documents no signing, credentials, orders, or account APIs. Phase 7 evidence recorded zero signed calls and zero orders.

### Data integrity and ledger truth: `PROVEN`

- `src/market/history.py:204-206` rejects duplicate, non-chronological, and bad-price history.
- `src/market/history.py:208-220` serializes measured gaps, missing funding, freshness, and funding anomalies.
- `src/ledger/events.py:22,70-105` enforces canonical identity and payload-hash validation.
- Replay-equality and atomicity tests are included in the verified suite.
- Venue reconciliation remains unproven because only public unauthenticated market data was allowed.

### UI truthfulness and responsive behavior: `NOT EVIDENCED`

- `ui/index.html:6-9` visibly labels the console read-only and identifies ledger sources.
- `ui/index.html:14` reads state through `GET /api/state` and reports unavailable state.
- Earlier Phase 6 browser evidence covered `360x800`, `390x844`, `768x844`, `1024x900`, and `1440x900` with zero measured overflow, but only an empty ledger.
- Populated-cycle rendering and populated table/card responsiveness were not independently evidenced in Phase 7.

## Verification status

- Public shadow smoke: `PASS` at the safety boundary but `PUBLIC_SHADOW_DEGRADED` at runtime. One unauthenticated call returned `TICKER_SCHEMA`, so zero cycles completed, zero entries/orders occurred, and it provides no forward performance evidence.
- Full suite: `python3 -m pytest -q --timeout=20 --timeout-method=thread` -> **314 passed**.
- Compile check: `python3 -m compileall -q src scripts tests` -> **PASS**.
- Preflight resource guard: `PASS`, no violations. Snapshot had 1,230,041,088 available bytes and 87.411% swap used, so work stayed bounded and sequential.
- Public calls were run through `scripts/resource_guard.py` with a 90 second timeout and 768 MB address-space limit.
- No signed smoke, demo order, live order, credential access, transfer, or withdrawal occurred.

## Limitations and next gate

The older windows are designated untouched holdouts, but these short samples do not establish broad regime coverage, confidence intervals, parameter stability, or performance concentration. The next gate is `RESEARCH_GATE_PARKED`.
