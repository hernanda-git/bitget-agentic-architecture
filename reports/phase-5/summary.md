# Phase 5 summary: deterministic strategy and research engine

## Gate verdict

`BLOCKED`: the deterministic baseline remains negative after fees, funding, and simulated slippage. Promotion is disabled, and Phase 6 must not begin.

## Raw verified run metrics

- Mode: `offline-paper-replay`
- Snapshots replayed: `36`
- Network calls: `0`
- Signed calls: `0`
- Orders: `37` (`36` entries, `1` typed end-of-replay reduce-only close)
- Open positions at replay end: `0`
- Closed trades: `36`
- End-of-replay closes: `1`
- Protection attachments: `36` paper positions configured with stop and target
- Reconciliation checks: `0` venue reconciliation checks; this is an offline simulator, not an exchange adapter
- Walk-forward protection attachments: `10` in window `[22,31]`, `3` in window `[33,35]`
- Walk-forward reconciliation checks: `0` in both windows
- Gross PnL: `-37.55597200000011`
- Fees: `3.398265286`
- Simulated slippage: `1.0559720000001107`
- Funding: `1.2428000000000003`
- Net PnL: `-43.25300928600022` (gross minus fees, slippage, and funding)
- Promotion allowed: `false`
- Promotion reason: `NEGATIVE_NET_PNL`
- Replay hash: `7fd9201588e765b283d38db03b5f46728ebef818891136fc87ddf11bf11b5e3c`
- Tests: `194 passed`, `0 failed`
- Network-data calls in this work unit: `0`

## Evaluation improvements

- Added explicit gross PnL and cost attribution by strategy and regime.
- Added expanding walk-forward test windows with an embargo and retained pre-test context while bounding execution and end-of-window flattening to each test window. Only complete test windows are reported; the fixture produced one complete window `[22,31]`, while the trailing 3-snapshot remainder is excluded rather than presented as a comparable result.
- Walk-forward net PnL was `-23.77089741000005` for the complete window `[22,31]`.
- Added per-window strategy attribution. In this fixture, all 10 complete-window closed trades were attributed to `trend_continuation`; `mean_reversion` and `volatility_breakout` produced zero closed trades.
- Fixed cost-stress funding attribution so configured funding assumptions affect replay cash costs while preserving fixture funding direction. Net PnL was `-42.19703728600011` at `1.0x`, `-44.8658073935001` at `1.5x`, and `-47.53474514400002` at `2.0x` cost assumptions; funding was `1.2428000000000003`, `1.8641999999999999`, and `2.4856000000000007` respectively.
- Corrected net funding attribution so funding received offsets funding paid rather than being incorrectly added to costs. The existing synthetic baseline is long-only and therefore unchanged; a regression test now verifies the signed funding arithmetic directly.
- Added strict walk-forward parameter validation (`0 < train_fraction < 1`, non-negative embargo, and positive test window) so malformed evaluation requests fail closed instead of silently changing the evaluation shape.
- Added a fail-closed minimum-data guard requiring at least one complete walk-forward test window; short datasets no longer return misleading partial-only evaluations.
- Added finite, positive cost-stress multiplier validation so zero, negative, NaN, infinity, and empty stress requests are rejected before replay.
- Corrected net PnL accounting to subtract simulated slippage, and exposed slippage in cost-stress and walk-forward reports. Replayed net PnL is `-43.25300928600022`; cost-stress net PnL is `-43.25300928600022`, `-46.2697653935002`, and `-49.28668914400004` at `1.0x`, `1.5x`, and `2.0x`.

## Implemented

- Versioned feature values with source snapshot identity and timestamp.
- Deterministic technical features and candidate generators.
- Candidate cost gate requiring expected move to exceed expected cost.
- Deterministic regime classification.
- Offline `FakeExchange` replay with typed `END_OF_REPLAY` flattening and fee, funding, and slippage accounting.
- Strategy/regime attribution, robust walk-forward evaluation, and cost stress reporting.

## Verification commands

```text
python3 scripts/resource_guard.py --json
python3 -m pytest tests/test_phase5_engine.py -q  # 12 passed
python3 -m pytest -q                             # 194 passed
python3 -m compileall -q src scripts tests
python3 scripts/run_strategy_baseline.py --output reports/phase-5/baseline.json
```

## Limitations and safety

The fixture is synthetic and adverse; it is not evidence of live profitability or loss rates. No public market-data call, signed call, demo call, live call, order, transfer, withdrawal, funded execution, or credential access occurred. The walk-forward runner evaluates replay-only test windows; it does not perform parameter fitting, venue reconciliation, or out-of-sample validation on independent market data. Funding stress is a configured deterministic rate proxy, not venue funding history. Phase 6 bounded LLM selection remains explicitly blocked.
