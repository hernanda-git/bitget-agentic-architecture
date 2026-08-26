# Phase 5 summary: deterministic strategy and research engine

## Gate verdict

`BLOCKED`: the deterministic baseline remains negative after fees, funding, bid/ask spread, and simulated execution slippage. Promotion is disabled, and Phase 6 must not begin.

## Raw verified run metrics

- Mode: `offline-paper-replay`
- Snapshots replayed: `36`
- Trading-runtime network calls: `0`
- Signed calls: `0`
- Runner-submitted paper orders: `16`
- Open positions at replay end: `0`
- Closed trades: `15`
- End-of-replay closes: `1`
- Protection attachments: `15`
- Reconciliation checks: `0`
- Walk-forward protection attachments: `10` in complete window `[22,31]`
- Walk-forward reconciliation checks: `0` in the complete window
- Gross PnL: `-20.0`
- Fees: `1.37750203`
- Spread: `0.30000000000013927`
- Simulated slippage: `0.5509999999999238`
- Funding: `0.40569999999999995`
- Net PnL: `-22.63420203000006`
- Promotion allowed: `false`
- Promotion reason: `NEGATIVE_NET_PNL`
- Replay hash: `7fd9201588e765b283d38db03b5f46728ebef818891136fc87ddf11bf11b5e3c`
- Tests: `222 passed`, `0 failed`
- Public market-data or exchange network calls in this work unit: `0`

## Runtime health verification

- Command: `python3 scripts/run_autonomous_paper.py --mode paper --cycles 3 --symbols BTCUSDT`
- Result: execution integrity `PASS`, runtime health `DEGRADED`
- Market-data variation: `FLATLINE` (`3` identical mark samples)
- Decision variation: `FLATLINE` (`3` identical `HOLD` outcomes)
- Orders: `0`; open positions: `0`; closed trades: `0`
- Fees: `0.0`; funding: `0.0`; gross PnL: `0.0`; net PnL: `0.0`
- Protection attachments: `0`; reconciliation checks: `0`
- Network calls: `0`; signed calls: `0`
- Limitation: the fixed offline HOLD fixture intentionally proves the detector and is not live market-data health evidence.
- Clean enter composition smoke: `1` cycle, `2` paper orders, `1` closed trade, `0` open positions, fees `0.020999999999999998`, funding `0.022`, gross PnL `2.0`, net PnL `1.957`, protection `1`, reconciliation `1`, network calls `0`, signed calls `0`, integrity `true`.

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
- Walk-forward net PnL was `-13.276751260000037` for the complete window `[22,31]`.
- Added per-window strategy attribution. In this fixture, all 10 complete-window closed trades were attributed to `trend_continuation`; `mean_reversion` and `volatility_breakout` produced zero closed trades.
- Fixed cost-stress funding attribution so configured funding assumptions affect replay cash costs while preserving fixture funding direction.
- Corrected net funding attribution so funding received offsets funding paid rather than being incorrectly added to costs.
- Corrected paper funding settlement for negative rates: long positions receive and short positions pay, with a regression test covering both directions.
- Attributed accrued paid or received funding to each closed FakeExchange trade, so aggregate replay accounting and paper trade records agree on fee-inclusive outcomes.
- Added strict walk-forward parameter validation and a fail-closed minimum-data guard requiring at least one complete test window.
- Added finite, positive cost-stress multiplier validation.
- Added a fail-closed Phase 5 artifact validator that compares detailed baseline JSON with compact summary fields and checked-in Markdown numerical claims, including separate spread attribution.
- Added replay-input data-quality validation: missing or stale snapshot hashes, mixed symbols, and regressing observed or source timestamps fail closed before evaluation.
- Added replay-input validation for chronological candle timestamps in both the primary candle list and populated candle windows; rehashed reordered history is rejected before walk-forward evaluation.
- Verified the offline composition root with FakeExchange: `2/2` paper cycles completed, `4` orders, `2` closed trades, no open positions, `2/2` protection reconciliation and verification, integrity `PASS`, and zero network or signed calls.
- Corrected protection-triggered paper fills to execute from the quoted bid or ask with configured adverse slippage instead of filling at mark and misclassifying the quote gap as slippage.
- Corrected typed end-of-replay closes to preserve the final executable bid and ask instead of erasing the final half-spread.
- Fail closed when a fresh armed bot monitor has no intended stop-loss or take-profit levels; missing protection now remains `DEGRADED` and parks entries.


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

The fixture is synthetic and adverse; it is not evidence of live profitability or loss rates. No public market-data call, signed call, demo call, live call, order, transfer, withdrawal, or credential access occurred. The walk-forward runner evaluates replay-only test windows; it does not perform parameter fitting, venue reconciliation, or out-of-sample validation on independent market data. Funding stress is a configured deterministic rate proxy, not venue funding history; the paper exchange handles positive and negative funding directions and attributes them to closed trades. Spread is derived from the fixture's bid/ask versus mark, and execution slippage is derived from the configured fill impact beyond the quoted side. The fixture contains repeated warm-up snapshots by design; validation permits equal timestamps and does not silently deduplicate them. Candle chronology is checked for the primary and populated window sequences, but this remains replay validation rather than live venue data-quality evidence. Phase 6 bounded LLM selection remains explicitly blocked.
