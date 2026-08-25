# Phase 2 summary: event-driven paper exchange

## Gate status

**PASS** for the offline Phase 2 gate. This is not a profitability claim and does not authorize demo or live execution.

## Implemented

- Typed `ExchangePort` and `MarketEventPort` interfaces.
- `VenueSpecification` with exact price/quantity/minimum-notional/leverage/margin validation.
- Deterministic `MarketEvent` model.
- Event-driven `FakeExchange` with `NEW`, `PARTIALLY_FILLED`, `FILLED`, `CANCEL_REQUESTED`, `CANCELLED`, `REJECTED`, and `EXPIRED` states.
- Market and resting-limit matching, partial fills, IOC expiry, duplicate IDs, rejection, spread crossing, slippage, reduce-only, funding, and balance reads.
- Exactly-once protection trigger behavior, including gap-through-stop, with mark progression.
- Fee-inclusive accounting function for gross PnL, entry/exit fees, funding, slippage, net PnL, and return on margin.
- Paper entry lifecycle now closes the deterministic target path before reporting success.
- Replay now reports closed trades, open positions, and replay net PnL.

## Raw verification evidence

| Check | Command | Result |
|---|---|---|
| RED | `pytest -q tests/test_phase2_exchange.py` before implementation | Collection failed as expected: missing `src.execution.ports` |
| GREEN | `pytest -q tests/test_phase2_exchange.py` | `7 passed` |
| Relevant suite | `pytest -q tests/test_phase2_exchange.py tests/test_fake_exchange.py tests/test_autonomous_paper_cli.py tests/test_service_hygiene.py tests/test_event_contracts.py` | `26 passed` |
| Full suite | `pytest -q` | `166 passed in 4.52s` |
| Compile | `python3 -m compileall -q src scripts tests` | exit `0` |
| Launcher | `python3 scripts/run_autonomous_paper.py --help` | exit `0` |
| Acceptance | `python3 scripts/run_autonomous_paper.py --mode paper --cycles 100 --scenario enter --ledger /tmp/paper-phase2.sqlite3 --reports-dir /tmp/paper-phase2-reports` | `PASS`, 100/100 cycles, zero anomalies |
| Replay | `python3 scripts/replay_ledger.py /tmp/paper-phase2.sqlite3` | exit `0`, 100 closed trades, no open positions |

Acceptance evidence: `network_calls=0`, `signed_calls=0`, `orders_are_fake=true`, `fees=10.994999999999969`, forced funding `=10.999999999999995`, runtime `net_pnl=-0.9950000000000008`, replay `net_pnl=-0.9950000000000008`.

## Limitations

- This is deterministic fake exchange behavior only. It does not validate a real venue or network path.
- Funding is forced by the acceptance scenario and recorded as an exchange balance cost; trade-level funding allocation remains minimal.
- The legacy `place_order` compatibility facade remains; event-driven callers should use `submit_order` and `apply_market_event`.
