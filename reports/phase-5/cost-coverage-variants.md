# Phase 5 research: cost-coverage entry viability gate

Date: 2026-08-26 (Asia/Jakarta, UTC+7)

## Gate verdict

`BLOCKED` (unchanged). The deterministic baseline remains negative after fees,
real funding, spread, and slippage at every tested edge-coverage level on both
stored public datasets. Promotion to Phase 6 bounded LLM selection stays
disabled. This unit was unblocked research/engineering only: `0` network calls,
`0` signed calls, `0` orders, `0` positions, `0` transfers, no credentials, no
connection to any deployed bot tree. All evaluation used the previously stored
public datasets in `data/history/`.

## What this work unit changed

Motivated by the honest finding in `expanded-history-evaluation.md`: candidates
enter whenever expected move barely exceeds expected cost, so nearly every
trade pays the full round-trip cost for a marginal edge.

1. `BaselineConfig.min_edge_coverage` (default `1.0`, behavior-preserving) added
   to `src/evaluation/baseline.py`. In `run_baseline`, a candidate whose
   `expected_move < min_edge_coverage * expected_cost` is skipped and counted.
   Validation fails closed: non-finite or `< 1.0` raises `ValueError`.
2. `BaselineResult.cost_gate_skipped` reports how many candidates the gate
   removed. Skips are counted and surfaced, never silent.
3. `run_coverage_variants(snapshots, config, coverages)` runs the identical
   replay under increasing coverage requirements and returns raw rows
   (orders, closed_trades, gross/fees/spread/slippage/funding/net,
   cost_gate_skipped, promotion_reason). It is measurement only: no variant
   changes the promotion gate.
4. `scripts/evaluate_real_history.py` embeds `cost_coverage_variants`
   (coverages 1.0 / 2.0 / 3.0) in its payload and prints `cost_gate_skipped`.

## TDD evidence

- RED: `tests/test_cost_coverage_gate.py` written first. First run failed with
  `ImportError: cannot import name 'run_coverage_variants'` (feature missing).
  After the dataclass fields existed but before wiring, the CLI test failed
  with `KeyError: 'cost_coverage_variants'`.
- GREEN: minimal implementation; focused files then passed (5/5 gate tests;
  52 across gate/public-history/engine).
- Full suite after all changes: `264 passed`
  (`.venv/bin/python -m pytest tests/ -q`), up from 258 (+6 new tests:
  5 gate + 1 CLI embedding).
- `compileall src scripts tests`: clean (exit 0).
- Mutation check: mutating the gate to `if False and ...` failed exactly
  `test_marginal_candidate_trades_by_default_and_is_skipped_at_coverage_two`;
  restoring the file returned 5/5 green. The assertions bind to the behavior.
  (First mutation attempt silently failed to apply and was re-applied with the
  proper tool before running; the accidental unmutated run was discarded.)
- Regression guard inside the new tests: coverage `1.0` reproduces the plain
  baseline result object exactly (`test_default_coverage_preserves_historical_
  behavior`) and the CLI's 1.0 variant must equal the stored baseline numbers.

## Raw verified metrics (replay accounting over stored public history)

Command pattern:

```text
.venv/bin/python scripts/evaluate_real_history.py --symbol <SYM> --granularity 5m \
    --output reports/phase-5/<artifact>.json     # dataset loaded from data/history/
```

Data quality re-checked at run time: both datasets ok=true, gaps=0,
funding_missing=0, funding_anomalies=0, bad_prices=0.

### BTCUSDT 5m, 6000 candles (~20.8 days), `reports/phase-5/real-data-5m-expanded.json`

| min_edge_coverage | orders | closed_trades | skipped | gross | fees+spread+slip+funding | net_pnl |
|---|---|---|---|---|---|---|
| 1.0 | 353 | 353 | 0 | +13222.50 | 38446.48 | **-25223.98** |
| 2.0 | 213 | 213 | 190 | +11355.60 | 22869.81 | **-11514.18** |
| 3.0 | 37 | 37 | 4284 | +3438.50 | 4134.05 | **-695.55** |

All variants: promotion_allowed=false, NEGATIVE_NET_PNL.

### ETHUSDT 5m, 6000 candles (~20.8 days), `reports/phase-5/real-data-5m-ethusdt.json`

| min_edge_coverage | orders | closed_trades | skipped | gross | fees+spread+slip+funding | net_pnl |
|---|---|---|---|---|---|---|
| 1.0 | 467 | 467 | 0 | +719.35 | 1563.24 | **-843.89** |
| 2.0 | 246 | 246 | 302 | +612.32 | 810.48 | **-198.16** |
| 3.0 | 61 | 61 | 3823 | +125.32 | 212.62 | **-87.29** |

All variants: promotion_allowed=false, NEGATIVE_NET_PNL.

The 1.0 rows reproduce the previous work unit's baselines exactly
(BTC -25223.98, ETH -843.89), confirming the default path is unchanged.

## Honest interpretation

- Stricter cost coverage monotonically reduces losses on both symbols by
  removing marginal entries; at coverage 3.0 BTC loses 97% less and ETH loses
  90% less than the unfiltered baseline. Gross PnL decays faster than trade
  count, i.e. filtered-out trades were disproportionately cost-losers.
- No tested coverage turns the deterministic baseline positive. The residual
  loss is concentrated in few remaining trades whose realized move still fails
  to cover costs. This is reported as measured; nothing was tuned to manufacture
  profitability, and the promotion gate is untouched by these variants.
- These numbers remain replay accounting over candle closes plus assumed
  half-spread and configured slippage; they are not exchange-proven execution.

## Protection / reconciliation / runtime facts

- Replay-only unit: every simulated entry attached deterministic SL/TP
  (`protection_attachments == closed_trades` asserted by the existing engine
  tests); reconciliation_checks remain 0 in this offline evaluator by design;
  runtime protection supervision is covered separately by
  `tests/test_protection_supervisor.py`, `tests/test_protection_reconciliation.py`,
  and `tests/test_mark_monitor.py`, all green in the 264-test suite.

## Limitations

- Coverage levels 2.0/3.0 were fixed a priori as round measurement points, not
  optimized; scanning finer grids would be tuning and was not done.
- Historical bid/ask is unavailable publicly; spread stays an assumed 0.5 bps
  half-spread charged in replay, not an observation.
- Venue funding history caps at 100 settlements (~covers these 21-day windows
  only). Longer histories would need incremental acquisition.
- The gate uses each generator's own `expected_move` estimate; it filters
  cost-marginal signals, it does not create edge that is not there.
