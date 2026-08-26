# Phase 3 summary: evaluation evidence and hypothesis registry

## Outcome

Implemented work units `3.1` through `3.4` offline without a commit.
Pre-existing modified and untracked workspace files were preserved.

- `3.1`: evaluator success payload now includes durable `funding_readiness`
  with `ok`, reason, in-range record count, expected settlement count, and
  missing count. Existing `real_funding_readiness` fail-closed semantics remain
  intact for absent and sparse coverage.
- `3.2`: added a named ten-dimension stress matrix. Every row reports closed
  trades, gross PnL, fees, funding, spread, slippage, net PnL, drawdown,
  promotion status, and reason. The implementation asserts a stress cannot add
  closed trades versus its plain baseline.
- `3.3`: added small-sample-aware descriptive statistics including expectancy,
  R expectancy, bootstrap CI, profit factor, drawdown/recovery, win/loss,
  tails, consecutive losses, stability group status, and concentration.
- `3.4`: added an independent validated hypothesis registry and
  `docs/STRATEGY_HYPOTHESES.md` with all required fields.

## Verification evidence

Commands and exact results:

```text
python3 -m pytest -q tests/test_phase3_evaluation.py tests/test_public_history.py tests/test_data_quality_strengthened.py tests/test_cost_coverage_gate.py
39 passed in 1.70s

python3 -m compileall -q src scripts tests
exit 0

python3 -m pytest -q
297 passed in 10.69s
```

Offline fixture replay produced 36 snapshots and 15 closed trades, with gross
PnL `-20.0`, net PnL `-22.63420203000006`, promotion `false`, and reason
`NEGATIVE_NET_PNL`. The stress matrix dimensions are:

`fee`, `spread`, `slippage`, `latency`, `partial_fill`, `skipped_fill`,
`spread_widening`, `funding`, `participation`, `stale_data`.

No network calls, signed calls, orders, credentials, or private keys were used;
no public-network evaluation was performed.

## Limitations and blockers

- Latency, partial-fill, participation, and stale-data stresses are conservative
  deterministic cost/coverage proxies, not venue microstructure replays.
- Statistics operate on aggregate net trade PnLs and are descriptive; they do
  not establish significance or profitability.
- Rejected real-history evaluator runs preserve the existing no-output contract;
  they fail closed with a durable reason in the rejection message. Successful
  outputs durably include `funding_readiness` counts and reason.
- Host capacity was constrained (`45%` root filesystem use, about `1.4 GiB`
  available memory, and about `74%` swap used), so work and tests were run
  sequentially.

## Next gate

Independent review of stress model fidelity, followed by an explicitly
authorized later public-history evaluation. Promotion remains blocked by the
negative deterministic baseline.
