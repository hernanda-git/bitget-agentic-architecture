# Phase 19 — Acquire more public history + fail-closed multi-symbol honest aggregation (unblocked)

**Generated (WIB / Asia/Jakarta):** 2026-08-27 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline evaluation-integrity engineering + public data acquisition, no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate explicitly lists `acquire more public historical data when needed`
and `strengthen walk-forward evaluation` as unblocked streams. The stored evidence
base was thin (BTCUSDT + ETHUSDT, 2000 candles each). This phase:

1. **Acquired more public history** — extended BTCUSDT and ETHUSDT to 2500 candles
   and added two new symbols (SOLUSDT, BNBUSDT) at 2500 candles each, all via the
   unauthenticated public Bitget `SUSDT-FUTURES` history endpoints. No credentials,
   no signed calls.
2. **Added a fail-closed multi-symbol aggregator** (`src/evaluation/multisymbol.py`)
   plus a durable runner (`scripts/run_multisymbol_baseline.py`) that folds every
   per-symbol deterministic-baseline result into ONE honest report without
   laundering the blocked baseline into a go-live claim. The aggregate always
   carries `selection_blocked=True` and self-validates with the recursive
   `assert_truthful` guard (Phase 18), so a nested overclaim inside any per-symbol
   result is refused.

## TDD cycle (strict)

- **RED:** `tests/test_multisymbol_baseline.py` (5 tests) written first, importing
  `src.evaluation.multisymbol` (did not exist). Run failed at collection:
  `ImportError: cannot import name 'aggregate_symbol_results' from
  'src.evaluation.multisymbol'` (feature absent, not a typo).
- **GREEN:** Implemented `aggregate_symbol_results` (fail-closed: input overclaim
  guard + output `assert_truthful` self-validation; `aggregate_promotion_allowed`
  only True when NOT blocked AND every symbol positive AND every symbol adequately
  sampled). The 5 tests -> 5 passed.
- **REFACTOR:** None required; the module is a small pure composition of the
  existing `report_honesty` guard.

## Raw tests (executed this run)

```text
pytest tests/test_multisymbol_baseline.py -v   -> 5 passed
pytest tests/ -q                                -> 421 passed (was 416; +5 new)
python3 -m compileall -q src scripts tests      -> exit 0 (clean)
```

## Mutation test (assertions are real, not decoration)

Disabled BOTH fail-closed guards in `aggregate_symbol_results` (the per-symbol
`find_overclaims` input check AND the final `assert_truthful(aggregate)` output
self-validation):

```text
pytest tests/test_multisymbol_baseline.py::test_aggregate_refuses_overclaiming_symbol
  -> FAILED (Failed: DID NOT RAISE ReportHonestyError)
```

Reverted -> 5 passed. The mutation broke exactly the overclaim assertion,
proving it binds to the real guarding logic, not to incidental behavior. (Note:
disabling only the input guard did NOT break the test, because the recursive
output guard from Phase 18 still catches the nested overclaim — a deliberate,
documented defense-in-depth backstop.)

## Network calls (public, unauthenticated, SUSDT-FUTURES only)

Per-symbol `request_evidence` from the emitted reports:

```text
BNBUSDT: requests=5 successes=5 failures=0 rate_limits=0 retries=0 signed_calls=0 credentials_used=False
BTCUSDT: requests=5 successes=5 failures=0 rate_limits=0 retries=0 signed_calls=0 credentials_used=False
ETHUSDT: requests=5 successes=5 failures=0 rate_limits=0 retries=0 signed_calls=0 credentials_used=False
SOLUSDT: requests=5 successes=5 failures=0 rate_limits=0 retries=0 signed_calls=0 credentials_used=False
```

All requests were unauthenticated public GETs to
`https://api.bitget.com/api/v2/mix/market/{candles,history-fund-rate}` for
product type `SUSDT-FUTURES`. **0 authenticated/signed calls. 0 credentials used.**
`USDT-FUTURES` was never referenced. The only venue product in the entire run is
`SUSDT-FUTURES`.

## Signed calls / orders / positions

- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed by this phase).
  This is public-data acquisition plus offline evaluation. No credentials, demo
  keys, or live keys were used. No signed exchange calls, transfers,
  withdrawals, or funded execution occurred.

## Trades / fees / funding / PnL (measurement facts, not realized PnL)

Cost-inclusive deterministic replay over the stored REAL public history:

| Symbol   | Candles | WF windows | Closed trades | Gross PnL | Fees     | Spread  | Slippage | Funding | Net PnL     | Adequate sample | Promotion |
|----------|---------|-----------|---------------|-----------|----------|---------|----------|---------|-------------|-----------------|-----------|
| BNBUSDT  | 2500    | 90        | 52            | 8.07      | 36.43    | 3.64    | 14.57    | 0.35    | -46.93      | True            | False     |
| BTCUSDT  | 2500    | 90        | 44            | 199.40    | 3469.52  | 346.95  | 1387.81  | 9.36    | -5014.24    | True            | False     |
| ETHUSDT  | 2500    | 90        | 80            | 35.25     | 198.02   | 19.80   | 79.21    | 0.31    | -262.10     | True            | False     |
| SOLUSDT  | 2500    | 90        | 145           | 7.24      | 14.39    | 1.44    | 5.76     | 0.02    | -14.37      | True            | False     |
| **AGG**  | —       | —         | **321**       | —         | —        | —       | —        | —       | **-5337.64** | —              | **False** |

Every per-symbol report carries `selection_blocked=True` and `report_honest=True`
(the Phase 17 guard fired and passed on each). The aggregate report:
`overall_net_pnl=-5337.64`, `overall_closed_trades=321`, `selection_blocked=True`,
`aggregate_promotion_allowed=False`, `aggregate_promotion_reason=POSITIVE_EVIDENCE_REQUIRED`.
These are measurement facts about the deterministic baseline strategy over real
public history; they are NOT realized PnL and do NOT flip the deterministic gate.

## Protection / reconciliation

- Not exercised by this phase (no positions were created), consistent with it
  being evaluation-only. Protection supervision and reconciliation read-back
  remain covered by their own suites, which are part of the 421 passing tests.
  The aggregator and runner never touch runtime trading state.

## Limitations (honest)

- Spread is represented by the documented `assumed_half_spread_bps=0.5` because
  historical bid/ask is not retrievable from the public API; it is reported as an
  assumption, never as observed data. Funding is modeled from REAL settlements
  observed in the public feed.
- BNBUSDT carried 114 zero-volume bars (measured, `price_integrity_ok=True`);
  this is a data fact, not a gate failure (the structural `ok` gate keys on
  duplicate/non-chronological/bad prices only).
- The negative net PnL is a measurement of the deterministic baseline strategy
  over the replayed public history; it is evidence about THAT strategy, not a
  market verdict. More data strengthens the robustness of the negative finding
  (the gate is fail-closed and consistent across 4 symbols and 321 trades), not
  a claim of universal unprofitability.
- The aggregate propagates each symbol's `adequate_sample` but, because
  `selection_blocked=True`, the aggregate promotion gate is False regardless;
  positive measurement is never, by itself, a go-live license in this repo.
- The `.json` per-symbol reports under `reports/phase-19/` are generated
  artifacts (real measurement output), kept for auditability and to feed the
  aggregator; they contain no secrets.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. The expanded, multi-symbol evidence base (4 symbols,
321 trades, all negative, all fail-closed gates passing) confirms the negative
baseline robustly and honestly. The new fail-closed aggregator guarantees that
adding more symbols in future can never launder the blocked baseline into a
go-live-looking aggregate. Unblocked research/engineering continues per the cron
mandate.
