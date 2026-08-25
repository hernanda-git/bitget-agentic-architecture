# Phase 5 summary: deterministic strategy and research engine

## Gate verdict

`BLOCKED`: the deterministic baseline remains negative after fees, funding, bid/ask spread, and simulated execution slippage. Promotion is disabled, and Phase 6 must not begin.

## Raw verified run metrics

- Mode: `offline-paper-replay`
- Snapshots replayed: `36`
- Trading-runtime network calls: `0`
- Signed calls: `0`
- Runner-submitted paper orders: `37` (`36` entries, `1` typed end-of-replay reduce-only close); protection-triggered internal close records are excluded from this counter
- Open positions at replay end: `0`
- Closed trades: `36`
- End-of-replay closes: `1`
- Protection attachments: `36` paper positions configured with stop and target
- Reconciliation checks: `0` venue reconciliation checks; this is an offline simulator, not an exchange adapter
- Walk-forward protection attachments: `10` in complete window `[22,31]`
- Walk-forward reconciliation checks: `0` in the complete window
- Gross PnL: `-36.5` (mark-to-mark before transaction costs)
- Fees: `3.3977537220000005` (calculated from executed prices)
- Spread: `0.720000000000347` (bid/ask cost, including the final executable quote)
- Simulated slippage: `1.3590999999998772` (execution impact beyond the quoted bid/ask)
- Funding: `1.2428000000000003`
- Net PnL: `-43.219653722000224` (gross minus fees, spread, slippage, and funding)
- Promotion allowed: `false`
- Promotion reason: `NEGATIVE_NET_PNL`
- Replay hash: `7fd9201588e765b283d38db03b5f46728ebef818891136fc87ddf11bf11b5e3c`
- Tests: `208 passed`, `0 failed`
- Public market-data or exchange network calls in this work unit: `0`

## Evaluation improvements

- Versioned feature values with source snapshot identity and timestamp.
- Deterministic technical features and candidate generators.
- Candidate cost gate requiring expected move to exceed expected cost.
- Deterministic regime classification.
- Offline `FakeExchange` replay with typed `END_OF_REPLAY` flattening and fee, funding, spread, and execution-slippage accounting.
- Corrected paper accounting so gross PnL is mark-to-mark and spread plus execution slippage are each charged exactly once. A focused regression test proves that zero configured execution slippage does not erase the separately measured spread and that increased slippage is not double-counted.
- Strategy/regime attribution, robust walk-forward evaluation, and cost stress reporting now expose spread separately from execution slippage.
- Added explicit gross PnL and cost attribution by strategy and regime.
- Added expanding walk-forward test windows with an embargo and retained pre-test context while bounding execution and end-of-window flattening to each test window. Only complete test windows are reported; the fixture produced one complete window `[22,31]`, while the trailing 3-snapshot remainder is excluded rather than presented as comparable evidence.
- Walk-forward net PnL was `-24.02105227000008` for the complete window `[22,31]`.
- Added per-window strategy attribution. In this fixture, all 10 complete-window closed trades were attributed to `trend_continuation`; `mean_reversion` and `volatility_breakout` produced zero closed trades.
- Fixed cost-stress funding attribution so configured funding assumptions affect replay cash costs while preserving fixture funding direction.
- Corrected net funding attribution so funding received offsets funding paid rather than being incorrectly added to costs.
- Corrected paper funding settlement for negative rates: long positions receive and short positions pay, with a regression test covering both directions.
- Attributed accrued paid or received funding to each closed FakeExchange trade, so aggregate replay accounting and paper trade records agree on fee-inclusive outcomes.
- Added strict walk-forward parameter validation and a fail-closed minimum-data guard requiring at least one complete test window.
- Added finite, positive cost-stress multiplier validation.
- Added a fail-closed Phase 5 artifact validator that compares detailed baseline JSON with compact summary fields and checked-in Markdown numerical claims, including separate spread attribution.
- Added replay-input data-quality validation: missing or stale snapshot hashes, mixed symbols, and regressing observed or source timestamps fail closed before evaluation.
- Corrected protection-triggered paper fills to execute from the quoted bid or ask with configured adverse slippage instead of filling at mark and misclassifying the quote gap as slippage.
- Corrected typed end-of-replay closes to preserve the final executable bid and ask instead of erasing the final half-spread.
- Fail closed when a fresh armed bot monitor has no intended stop-loss or take-profit levels; missing protection now remains `DEGRADED` and parks entries.
- Verified a 100-cycle offline paper runtime smoke: `200` symbol cycles executed with no crash, no open positions, `PROTECTED` protection, `IN_SYNC` reconciliation, and zero network or signed calls.
- Mutation checks restored the prior protection-monitor guard, protection fill price, and end-of-replay quote handling; each corresponding regression test failed under mutation and passed after restoration.

## Implemented

- Versioned feature values with source snapshot identity and timestamp.
- Deterministic technical features and candidate generators.
- Candidate cost gate requiring expected move to exceed expected cost.
- Deterministic regime classification.
- Offline `FakeExchange` replay with typed `END_OF_REPLAY` flattening and fee, funding, spread, and execution-slippage accounting.
- Strategy/regime attribution, robust walk-forward evaluation, cost stress reporting, and synchronized evidence validation.

## Verification commands

```text
python3 scripts/resource_guard.py --json
python3 -m pytest tests/test_phase2_exchange.py::test_trade_accounting_separates_spread_and_execution_slippage -q
python3 -m pytest tests/test_phase5_engine.py tests/test_phase5_report.py -q
python3 -m pytest -q
python3 -m compileall -q src scripts tests
python3 scripts/run_strategy_baseline.py --output reports/phase-5/baseline.json
python3 scripts/verify_phase5_report.py --root .
```

## Limitations and safety

The fixture is synthetic and adverse; it is not evidence of live profitability or loss rates. No public market-data call, signed call, demo call, live call, order, transfer, withdrawal, funded execution, or credential access occurred. The walk-forward runner evaluates replay-only test windows; it does not perform parameter fitting, venue reconciliation, or out-of-sample validation on independent market data. Funding stress is a configured deterministic rate proxy, not venue funding history; the paper exchange handles positive and negative funding directions and attributes them to closed trades. Spread is derived from the fixture's bid/ask versus mark, and execution slippage is derived from the configured fill impact beyond the quoted side. The fixture contains repeated warm-up snapshots by design; validation permits equal timestamps and does not silently deduplicate them. Phase 6 bounded LLM selection remains explicitly blocked.
