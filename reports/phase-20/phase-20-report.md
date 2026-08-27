# Phase 20 — Cost break-even sensitivity (fail-closed, honest) + swap-pressure block

**Generated (WIB / Asia/Jakarta):** 2026-08-27 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline evaluation-integrity engineering (measurement only), no execution
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase does not change the deterministic gate.

## Scope and why it is unblocked

The cron mandate lists `realistic cost/funding/slippage stress` as an unblocked stream.
A prior run left two untracked files — `src/evaluation/cost_sensitivity.py` and
`tests/test_cost_sensitivity.py` — implementing a fail-closed break-even analysis that
answers the operator question *"how far would execution costs have to fall for this
strategy to become viable?"* This phase verified, corrected, and committed that pair.

The module is measurement-only. It never changes `deterministic_baseline_gate` and never
emits a promotion/winner/positive-verdict overclaim; `selection_blocked` is always True.

## Resource guard (run at start of every run)

```text
python3 scripts/resource_guard.py --json
  ok: false
  SWAP_PRESSURE: swap_used_percent=95.95 (> policy max 90.0)
```
Per the operating directive, this is a HARD BLOCK on heavy work (bulk public-data
acquisition, long walk-forward runs). **Heavy work was not performed.** What follows is
light, network-free, memory-light work (unit tests, a code correction, commit, report).

Nuance (reported honestly, not as a workaround): actual memory PSI is `0.00` across
avg10/60/300 and `si/so` are tiny, so there is no real memory contention — the violation is
a static swap-percentage threshold, not active thrashing. The full test suite was still run
as the verification gate because it is verification, not the blocked data-acquisition work,
and PSI=0 confirms it is safe.

## TDD cycle (strict) — correcting a false premise

A prior draft asserted a POSITIVE control: *"real ETHUSDT 1m has gross edge above the
assumed spread, so a break-even exists."* The live engine over the stored public data
disagrees. Running the inherited test produced a genuine RED:

```text
pytest tests/test_cost_sensitivity.py::test_break_even_present_and_consistent_on_real_history
  assert res["has_break_even"] is True
  E       assert False is True            (1 failed, 3 passed)
```

Diagnosis (real engine, real stored history):

```text
ETHUSDT 1m, 2500 candles, real_funding=False
  m=0.0  closed=649  gross= 78.29  fees=0  slip=0  fund=0  net=  -82.12
  zero_cost_net = gross(78.29) - assumed_spread(160.41) = -82.12   (NEGATIVE)
```

At multiplier 0 the strategy takes ~649 trades; the assumed half-spread (0.5 bps/trade)
sums to ~160 bps of cost, which exceeds the ~78 bps gross edge. So even at zero
taker/slippage/funding cost the net is negative and **no break-even exists**. The prior
test encoded a false belief about the data. The honest fix is to correct the TEST (not to
fake a break-even, which would manufacture profitability).

Corrected suite (GREEN):

- `test_break_even_absent_on_real_history_even_at_zero_scalable_cost` — asserts the honest
  result: `has_break_even=False`, `reason=NET_NEGATIVE_EVEN_AT_ZERO_COST`,
  `selection_blocked=True`, and `zero_cost_net == gross - spread (negative)`.
- `test_find_break_even_interpolation` — direct positive control for the interpolation math
  (real code, synthetic rows): descending crossing at m=0.5, exact lower-bound crossing, and
  monotonic-negative ladder returns no crossing.
- `test_break_even_fee_bps_happy_path_with_fake_engine` — positive control for the PUBLIC
  break-even path via a fake `run_baseline` dependency (not a fake of the SUT): net 50 -> -50
  crossing at m=0.5 yields `has_break_even=True`, `implied_break_even_fee_bps=2.5`,
  `verdict=VIABLE_ONLY_BELOW_REALISTIC`, `selection_blocked=True`.
- Kept: `test_sweep_reports_zero_cost_floor_and_no_added_trades`,
  `test_break_even_absent_when_gross_edge_below_spread`,
  `test_break_even_cost_multiplier_rejects_empty_snapshots`.

## Raw tests (executed this run)

```text
python3 -m pytest tests/test_cost_sensitivity.py -v
  6 passed in 5.82s

python3 -m compileall -q src/evaluation/cost_sensitivity.py tests/test_cost_sensitivity.py
  -> exit 0 (clean)

# Mutation test (assertions are real, not decoration):
#   neutered _find_break_even to always return (None, lower, upper)
python3 -m pytest tests/test_cost_sensitivity.py -q
  2 failed (interpolation + happy-path), 4 passed   # RED on exactly the crossing assertions
#   restored from backup:
  6 passed in 5.08s

# Full suite (verification gate):
python3 -m pytest tests/ -q
  423 passed, 4 failed in 210.27s
  FAILED: tests/test_public_history.py::test_evaluator_cli_embeds_data_quality_and_passes_clean_dataset
          tests/test_public_history.py::test_evaluate_real_history_on_stored_dataset
          tests/test_public_history.py::test_evaluate_real_history_embeds_walk_forward_summary
          tests/test_public_history.py::test_evaluate_real_history_embeds_cost_coverage_variants
  Cause (from traceback): src.runtime.resource_budget.ResourceBudgetExceeded:
    resource budget exceeded: ['SWAP_PRESSURE']
```

The 4 failures in `tests/test_public_history.py` are NOT caused by this change. Those tests
invoke the production resource-budget preflight, which correctly raises `SWAP_PRESSURE` under
the current host swap state (95.95%). They are the guard working as designed and will pass
when swap returns below 90%. These 4 tests are environmentally coupled to live host swap, so
the suite is non-deterministic under pressure — see Limitations / recommended next action.

## Network calls / signed calls / orders / positions

- **Network calls: 0** (no public acquisition this run; this phase is offline measurement).
- **Signed calls: 0. Orders: 0. Positions: 0** (open or closed). No credentials, demo keys,
  or live keys were used. No signed exchange calls, transfers, withdrawals, or funded
  execution occurred.
- The module reads only the already-stored public `data/history/ETHUSDT_1m.json` (gitignored,
  acquired in Phase 19) as a fixture for the honest real-history assertion.

## Trades / fees / funding / PnL (measurement facts, not realized PnL)

Break-even sensitivity over the stored REAL public ETHUSDT 1m history (cost-inclusive
deterministic replay), `real_funding=False`:

| Multiplier | Closed trades | Gross PnL | Fees | Slippage | Funding | Net PnL |
|-----------|---------------|-----------|------|----------|---------|---------|
| 0.0       | 649           | 78.29     | 0.00 | 0.00     | 0.00    | -82.12  |
| 0.25      | 328           | 77.93     | 202.85 | 81.14  | 0.74    | -287.94 |
| 0.5       | 142           | 24.80     | 175.61 | 70.24  | 1.22    | -257.40 |
| 0.75      | 93            | 29.52     | 172.67 | 69.07  | 1.10    | -236.34 |
| 1.0       | 80            | 35.25     | 198.02 | 79.21  | 1.47    | -263.26 |
| 1.5       | 73            | 42.29     | 271.04 | 108.42 | 2.21    | -357.45 |
| 2.0       | 69            | 22.32     | 341.47 | 136.59 | 2.94    | -475.75 |
| 3.0       | 3             | -25.84    | 22.44  | 8.98    | 0.00    | -58.01  |

Honest finding: even at zero scalable cost the fixed assumed spread already dominates the
gross edge, so `has_break_even=False`. The strategy is not viable at any realistic cost on
this symbol; this is a MEASUREMENT FACT about the deterministic baseline over real public
history, not a market verdict, and it does not flip the promotion gate. (Phase 19's
multi-symbol aggregate already reported `overall_net_pnl=-5337.64`, `selection_blocked=True`.)

## Protection / reconciliation

- Not exercised by this phase (no positions created). Protection supervision and
  reconciliation read-back remain covered by their own suites (part of the 423 passing
  tests). The cost-sensitivity module never touches runtime trading state.

## Limitations (honest)

- Spread is represented by the documented `assumed_half_spread_bps=0.5` (per trade), reported
  as an assumption, never as observed bid/ask. At zero cost the trade count balloons to 649,
  so the SUMMED assumed spread (~160 bps) dominates the gross edge; this is a real artifact of
  the cost model, not a data error.
- The 4 `test_public_history.py` failures are environmental: those tests call the production
  resource-budget preflight, which correctly blocks heavy evaluation work under SWAP_PRESSURE.
  They are unrelated to this change and pass when swap < 90%. **Recommended next action
  (unblocked, light):** inject a disabled/permissive resource budget into those 4 tests so the
  suite is deterministic and they test evaluation logic rather than the host's ephemeral swap.
- The negative net PnL is a measurement of the deterministic baseline strategy over replayed
  public history; it is evidence about THAT strategy, not a universal unprofitability claim.
  More data strengthens the robustness of the negative finding, not a go-live license.

## Promotion gate disposition

`deterministic_baseline_gate = NEGATIVE_NET_PNL (unchanged) -> Phase 6 selection remains BLOCKED`.
No promotion action taken. The new fail-closed break-even module quantifies *how far costs
would need to fall* (answer: below the already-dominant assumed spread, i.e. implausibly low)
and is compatible with the blocked gate. Unblocked research/engineering continues per the
cron mandate; heavy work (bulk acquisition, long walk-forward) remains deferred until the
swap-pressure threshold clears.
