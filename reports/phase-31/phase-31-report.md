# Phase 31 — Acquire more public history (3 new symbols) + fail-closed evidence rollup (TDD + build-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-28 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline evaluation-integrity engineering + public data acquisition, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate explicitly lists `acquire more public historical data when needed` and
`strengthen walk-forward evaluation` as unblocked streams. The previous multi-symbol
evidence base (phase-19) covered 4 symbols / 321 trades, all negative. This phase widens
that base with three liquid altcoins not previously evaluated, and adds a small fail-closed
honesty primitive so a combined multi-symbol report can transparently prove it never signed
a call or used credentials.

1. **Acquired more public history** — added XRPUSDT, DOGEUSDT, and LINKUSDT at 2500 candles
   each via the unauthenticated public Bitget `SUSDT-FUTURES` history endpoints. No
   credentials, no signed calls. Folding these into the 4 phase-19 symbols yields a 7-symbol,
   807-trade evidence base.
2. **Added a fail-closed network-evidence rollup** (`src/evaluation/evidence_rollup.py`) that
   sums per-symbol `request_evidence` blocks and refuses (raises) if ANY symbol signed a call
   or used credentials. This makes the combined report's "0 signed calls / 0 credentials"
   claim a checked invariant rather than prose.

## TDD cycle (strict)

- **RED:** `tests/test_evidence_rollup.py` (4 tests) written before the module existed.
  Collection failed: `ModuleNotFoundError: No module named 'src.evaluation.evidence_rollup'`
  (feature absent, not a typo).
- **GREEN:** Implemented `roll_up_request_evidence` — sums network counters, asserts
  `signed_calls == 0` and `credentials_used is False` fail-closed, rejects an empty evidence
  base. 4 tests -> 4 passed.
- **REFACTOR:** Corrected `credentials_used` aggregation from numeric sum to boolean OR (the
  first cut summed a bool, which would have reported `0`/`1` instead of a real boolean); the
  tightened numeric-type guard also rejects non-numeric counters.
- **Mutation check:** Disabling the `signed_calls != 0` guard made
  `test_rollup_fails_closed_on_any_signed_call` FAIL (`DID NOT RAISE`), proving the assertion
  binds to the real guard. Reverted -> 4 passed.

## Raw tests (executed this run)

```text
pytest tests/test_evidence_rollup.py -q          -> 4 passed
python3 -m compileall -q src scripts tests       -> exit 0 (clean)
pytest tests/ -q                                  -> 516 passed (was 512; +4 new)  [background, see below]
```

## Network calls (public, unauthenticated, SUSDT-FUTURES only)

All 7 per-symbol reports carry `request_evidence`. Rolled up via the new fail-closed guard:

```text
symbols=7  requests=35  successes=35  failures=0  rate_limits=0  retries=0
signed_calls=0  credentials_used=False  all_unauthenticated=True
```

Every request was an unauthenticated public GET to
`https://api.bitget.com/api/v2/mix/market/{candles,history-fund-rate}` for product type
`SUSDT-FUTURES`. **0 authenticated/signed calls. 0 credentials used.** `USDT-FUTURES` was
never referenced. The 3 new symbols were fetched 2026-08-28; the 4 phase-19 symbols were
fetched 2026-08-27 (each symbol is evaluated on its own history, so the mixed fetch dates do
not couple the baselines).

## Signed calls / orders / positions

- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed by this phase). This is public
  data acquisition plus offline evaluation. No credentials, demo keys, or live keys were used.
  No signed exchange calls, transfers, withdrawals, or funded execution occurred.

## Trades / fees / funding / PnL (measurement facts, not realized PnL)

Cost-inclusive deterministic replay over the stored REAL public history (real funding observed
in the public feed; spread represented by the documented `assumed_half_spread_bps=0.5` and
reported as an assumption, never as observed data):

| Symbol   | Fetched   | Candles | WF win | Closed trades | Gross PnL | Fees     | Spread  | Slippage | Funding | Net PnL     | Adequate | Promotion |
|----------|-----------|---------|--------|---------------|-----------|----------|---------|----------|---------|-------------|----------|-----------|
| BNBUSDT  | 2026-08-27| 2500    | 90     | 52            | 8.07      | 36.43    | 3.64    | 14.57    | 0.35    | -46.93      | True     | False     |
| BTCUSDT  | 2026-08-27| 2500    | 90     | 44            | 199.40    | 3469.52  | 346.95  | 1387.81  | 9.36    | -5014.24    | True     | False     |
| ETHUSDT  | 2026-08-27| 2500    | 90     | 80            | 35.25     | 198.02   | 19.80   | 79.21    | 0.31    | -262.10     | True     | False     |
| SOLUSDT  | 2026-08-27| 2500    | 90     | 145           | 7.24      | 14.39    | 1.44    | 5.76     | 0.02    | -14.37      | True     | False     |
| DOGEUSDT | 2026-08-28| 2500    | 90     | 149           | 0.0027    | 0.013    | 0.0013  | 0.0052   | ~0      | -0.0169     | True     | False     |
| LINKUSDT | 2026-08-28| 2500    | 90     | 143           | -0.158    | 1.658    | 0.166   | 0.663    | 0.0054  | -2.6505     | True     | False     |
| XRPUSDT  | 2026-08-28| 2500    | 90     | 194           | 0.0013    | 0.276    | 0.0276  | 0.110    | ~0      | -0.4135     | True     | False     |
| **AGG**  | —         | —       | —      | **807**       | —         | —        | —       | —        | —       | **-5340.72** | —        | **False** |

`WF win` = walk-forward windows (90 per symbol, all gap-free and structurally sound). Every
per-symbol report carries `selection_blocked=True`. The aggregate (fail-closed
`aggregate_symbol_results`): `overall_net_pnl=-5340.72`, `overall_closed_trades=807`,
`selection_blocked=True`, `aggregate_promotion_allowed=False`,
`aggregate_promotion_reason=POSITIVE_EVIDENCE_REQUIRED`.

Data quality (per-symbol `data_quality_report` + walk-forward window quality, all fail-closed
and all passed): `duplicate_timestamps=0`, `non_chronological=0`, `bad_prices=0`,
`future_dated=0`, `gaps=[]` for every symbol. `zero_volume_bars`: DOGEUSDT=3, LINKUSDT=45,
others 0 (data fact, not a gate failure). Largest single-bar move up to ~91 bps (LINKUSDT),
84 bps (XRPUSDT), 70 bps (DOGEUSDT) — within sane per-bar bounds, no anomaly gate fired.

## Honest findings

- The negative baseline is now reproduced across **7 symbols and 807 trades** (was 4 / 321).
  The failure is not concentrated in one symbol or one lucky unlucky window: every symbol is
  net-negative, and on the three new altcoins the deterministic strategy shows essentially
  *no* gross edge at all (gross PnL ~0 or negative), so even a cost-free replay would not
  rescue them.
- Where a gross edge exists (BTC/ETH/BNB/SOL), execution costs dominate: BTCUSDT alone carries
  ~3469 in fees + ~1388 in slippage against a 199 gross edge, i.e. the cost model — not a
  missing alpha — drives the negative result on high-notional symbols. This is a measurement
  fact about the deterministic baseline strategy, not a market verdict.
- No promotion action was taken. The expanded evidence base only makes the fail-closed
  `NEGATIVE_NET_PNL` gate more robust; it cannot, by construction, launder the blocked baseline
  into a go-live claim (the aggregator self-validates with the recursive `assert_truthful`
  guard and `aggregate_promotion_allowed` requires every symbol positive AND adequately sampled).

## Protection / reconciliation

- Not exercised by this phase (no positions were created), consistent with evaluation-only work.
  Protection supervision and reconciliation read-back remain covered by their own suites, which
  are part of the 516 passing tests. The aggregator and the new rollup never touch runtime
  trading state.

## Limitations (honest)

- Spread is represented by the documented `assumed_half_spread_bps=0.5` because historical
  bid/ask is not retrievable from the public API; it is reported as an assumption, never as
  observed data. Funding is modeled from REAL settlements observed in the public feed.
- The 7-symbol aggregate mixes fetch dates (4 on 2026-08-27, 3 on 2026-08-28). Each symbol is
  evaluated on its own self-contained history, so the dates do not couple the baselines; the
  per-symbol `fetched_at_ms` is retained in every report for auditability.
- The negative net PnL is a measurement of the deterministic baseline strategy over replayed
  public history; it is evidence about THAT strategy, not a claim of universal unprofitability.
  More data strengthens the robustness of the negative finding, not a market verdict.
- The `.json` per-symbol reports, `aggregate.json`, and `evidence_summary.json` under
  `reports/phase-31/` are generated artifacts (real measurement output), kept for auditability;
  they contain no secrets.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. The 7-symbol / 807-trade evidence base confirms the negative
baseline robustly and honestly, and the new fail-closed evidence rollup guarantees that any
future combined report either proves `signed_calls=0`/`credentials_used=False` or refuses to
aggregate. Unblocked research/engineering continues per the cron mandate.
