# Phase 3 summary: deterministic sizing and portfolio risk

## Outcome

Phase 3 is implemented and verified locally. This phase does **not** claim profitability or any funded/demo capability.

## TDD evidence

- RED: `python3 -m pytest -q tests/test_phase3_risk.py`
  - Expected collection failure: `ModuleNotFoundError: No module named 'src.risk'`.
- GREEN: `python3 -m pytest -q tests/test_phase3_risk.py`
  - `7 passed`.

## Implementation

- Added `src/risk/portfolio.py` and `src/risk/exposure.py`.
- Added account/portfolio facts for equity, available/used margin, gross/net/long/short notional, positions by symbol, realized daily PnL, unrealized PnL, fees, funding, peak equity, and drawdown.
- Added SQLite `portfolio_snapshots` projection with restart round-trip coverage.
- Added explicit finite risk limits in `src/config.py` and `config.example.yaml`; policy mappings reject missing executable limits and infinite/non-positive values.
- Extended sizing for contract multiplier, available equity, existing exposure, total-notional room, venue step/minimum/max constraints, and stop distance.
- Wired `size_for_risk()` into both entry implementations: `src/paper_loop.py` and `src/runtime/paper_runtime.py`.
- Provider quantity is rejected by the sizing API and is not part of the accepted decision schema. Durable focused tests prove the bypass path fails.
- Existing effective-risk reporting remains venue-adjusted and reports requested risk, actual quantity/notional, stop distance, realized risk, equity/daily-cap ratios, and minimum-notional distortion.
- Added gross, net, correlated, and symbol concentration gates in both pure exposure checks and semantic policy state.

## Verification evidence

- Relevant tests: `31 passed`.
- Full suite: `python3 -m pytest -q` -> `173 passed`.
- Compile: `python3 -m compileall -q src scripts tests` -> passed.
- Entrypoint: `python3 scripts/run_autonomous_paper.py --help` -> passed.
- Paper run: `python3 scripts/run_autonomous_paper.py --mode paper --cycles 100 --scenario enter --ledger /tmp/phase3-paper.sqlite3 --reports-dir /tmp/phase3-paper-reports` -> exit `0`, `100/100` cycles, `100` closed trades, `0` open positions, `fees=2.1989999999999936`, `funding=2.1999999999999993`, `net_pnl=-0.19900000000000131`, `network_calls=0`, `signed_calls=0`, `integrity_ok=true`.
- Replay: `python3 scripts/replay_ledger.py /tmp/phase3-paper.sqlite3` -> completed, `open_positions=[]`, replay net PnL `-0.19900000000000131`.
- `git diff --check` -> passed.

## Safety and limitations

- No network calls, credentials, exchange calls, demo orders, or funded mode were used.
- The paper smoke test is an engineering result, not a profitability claim; its fee-inclusive net PnL was negative.
- Portfolio snapshots are durable ledger projections, but the runtime does not yet automatically append a snapshot after every fill cycle.
- Correlation is configured-matrix based; rolling-return correlation is deferred.

## Next gate

Phase 4: corrected market data and public shadow, retaining zero signed calls and zero orders.
