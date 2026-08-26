# Phase 5 — data-quality hardening (strengthened checks)

Work unit: extend the historical `DataQualityReport` with price-integrity,
staleness, single-bar-outlier, and funding-anomaly checks. Strict TDD
(failing test first, RED, minimal GREEN, full suite, compileall, mutation check).

## Scope and gate status
- Deterministic baseline remains `NEGATIVE` (prior run). Promotion stays `BLOCKED`.
- Phase 6 (bounded LLM selection) remains blocked. This unit continues unblocked
  research/engineering on data quality and evaluation robustness.
- No live or demo credentials, no signed calls, no orders, no transfers, no funded
  execution. Public market history is read only from local `data/history`.

## What changed
- `src/market/history.py` `DataQualityReport` now carries: `bad_prices`,
  `data_age_ms`, `max_data_age_ms`, `max_single_bar_return_bps`, `funding_anomalies`,
  plus `price_integrity_ok` and `freshness_ok` properties.
- `ok` now also fails on `bad_prices > 0` (structural soundness = chronology +
  price integrity).
- `data_quality_report(...)` accepts `max_data_age_ms` (freshness gate) and
  `max_funding_rate` (anomaly bound, default 5%).
- `scripts/evaluate_real_history.py` applies the gate, surfaces the new facts on
  the success line, and rejects with a fuller `DATA_QUALITY_REJECTED` reason
  including `bad_prices` and `funding_anomalies`. Adds `--max-data-age-ms`.

## TDD evidence
- RED: `tests/test_data_quality_strengthened.py` written first, 7 tests failed
  (missing fields / unexpected keyword `max_data_age_ms`).
- GREEN: implemented minimal checks; 7/7 pass.
- Full suite: `258 passed` (was 251; +7 new). No regressions.
- `compileall` on `src scripts tests`: clean (exit 0).
- Mutation check: disabling the non-finite guard (`bad_prices += 1` -> `if False`)
  broke exactly `test_data_quality_flags_non_finite_prices` and
  `test_data_quality_flags_bad_prices_and_fails_structural_ok`; reverting restored
  green. Assertions bind to behavior.

## Raw verified metrics (real stored public history)
No network calls, no signed calls, no orders, no positions, no trades, no fees,
no funding charged (report-only measurement).

| symbol | candles | funding recs | bad_prices | ok | price_integrity_ok | data_age_ms | max_data_age_ms | freshness_ok | max_single_bar_return_bps | gaps | max_missing_bars | zero_volume_bars | funding_missing | funding_anomalies | report_compute_sec |
|--------|---------|--------------|------------|----|--------------------|-------------|-----------------|--------------|---------------------------|------|------------------|------------------|-----------------|-------------------|--------------------|
| BTCUSDT_5m | 6000 | 100 | 0 | True | True | 88544 | 3600000 | True | 181.91 | 0 | 0 | 0 | 0 | 0 | 0.007 |
| ETHUSDT_5m | 6000 | 100 | 0 | True | True | 26450 | 3600000 | True | 355.13 | 0 | 0 | 0 | 0 | 0 | 0.007 |

Interpretation:
- Both stored datasets pass the hardened gate (no non-finite prices, chronologically
  clean, funding covered, fresh within the 1h gate).
- The largest single-bar close-to-close moves (BTC 181.91 bps, ETH 355.13 bps) are
  reported as measured outliers for downstream review; they are within plausible
  intraday range for 5m bars and do not trip a hard gate (no threshold asserted yet
  by design — outliers are surfaced, not silently dropped).
- The full `run_baseline`/`run_walk_forward`/`run_cost_stress` replay over the full
  6000-candle stored datasets was NOT executed here: it exceeded the 180s harness
  timeout on the prior attempt and is not required to verify the data-quality gate.
  The gate path through the CLI entrypoint is covered by
  `test_evaluator_cli_embeds_data_quality_and_passes_clean_dataset` (passes, rc 0)
  and `test_evaluator_cli_fails_closed_on_bad_prices` (rejects, rc != 0).

## Limitations
- Price-integrity detection targets non-finite values (NaN/inf slip past
  `Candle.__post_init__` because every comparison with them is `False`). Impossible
  OHLC geometry and non-positive prices are already rejected at `Candle` construction,
  so they cannot reach this report through the normal load path; the gate remains
  defense-in-depth for the finite-but-invalid case.
- No hard outlier threshold is enforced; single-bar extremes are measured and
  surfaced only. A future unit can add a configurable outlier gate if research shows
  it improves walk-forward robustness.
- The freshness gate is opt-in (`--max-data-age-ms`); without it, staleness is
  reported but not a hard rejection, so long-stored datasets remain evaluable.
