# Phase 27 — Runtime heartbeat / stall monitor (TDD + build-verification)

**Date:** autonomous cron run (Asia/Jakarta timezone)
**Mode:** offline, no network, no credentials, no orders, no signed calls.
**Scope:** detect daemon *liveness regression* fail-closed, independent of market data.

## Why this unit exists

The build-verification skill documents a real trap: a daemon can emit perfectly-formed,
perfectly-constant payloads forever and pass every health check while computing nothing.
`systemctl is-active` + HTTP 200 prove only that the process runs, not that it produces
cycles. A flat-line metric is a *suspected broken metric*, not a market read.

This unit adds a `HeartbeatMonitor` that parks new entries when the autonomous runtime
stops completing cycles for longer than `max_gap_ms`. It is wired to the existing
`heartbeat` entry circuit breaker and supports a *verified automatic recovery*: a fresh
heartbeat (a real completed cycle observed by the runtime monitor) clears its own trip.
The model can never clear a breaker; only an `operator` or `auto_recovery` actor may.

## TDD cycle

RED first: `tests/test_runtime_heartbeat.py` written before the implementation was
correct. The initial `HeartbeatMonitor.status()` had an inverted boundary
(`HEALTHY` when `gap > max_gap_ms`), so the tests were RED.

GREEN: minimal one-line fix flipped the comparison so a stall is declared only when
`gap > max_gap_ms`; exactly at the boundary (`gap == max_gap_ms`) stays HEALTHY.

```
- return "HEALTHY" if (now - self._last_beat_ms) > self.max_gap_ms else "STALLED"
+ return "STALLED" if (now - self._last_beat_ms) > self.max_gap_ms else "HEALTHY"
```

The breaker `clear()` actor allow-list was also extended from `("operator",)` to
`("operator", "auto_recovery")` (test-first in `tests/test_breakers.py`), so a verified
automatic recovery can un-park entries after a stall recovers while the model still cannot.

## Raw tests

```
$ python3 -m pytest tests/test_runtime_heartbeat.py tests/test_breakers.py -q
............... 15 passed in 0.04s

$ python3 -m pytest tests/ -q
495 passed in 209.39s
```

Runtime health report (build-verification: drive the monitor over a simulated timeline):

```
$ python3 scripts/run_runtime_health_report.py
now_ms  beat   status    parked  reason
0        True   HEALTHY   False   -
500      True   HEALTHY   False   -
1000     True   HEALTHY   False   -
2000     False  HEALTHY   False   -
3000     False  STALLED   True    no heartbeat for 2000ms (max 1000ms)
4000     False  STALLED   True    no heartbeat for 2000ms (max 1000ms)
5000     False  STALLED   True    no heartbeat for 2000ms (max 1000ms)
6000     True   HEALTHY   False   -
6500     True   HEALTHY   False   -
RUNTIME_HEALTH_OK: stall parked entries; fresh heartbeat recovered.
EXIT=0
```

## Behaviors covered (one per test)

- cold start is `UNKNOWN`, never `STALLED` (a fresh runtime is not parked before its first cycle)
- `HEALTHY` exactly at and within the gap boundary
- `STALLED` one ms past the boundary; `should_park()` true (fail-closed)
- rejects non-positive `max_gap_ms` and regressed heartbeat timestamps
- a stall trips the `heartbeat` breaker and parks entries; trip attributed to the monitor
- a fresh heartbeat after a stall clears the breaker via `auto_recovery`
- the monitor never clears an operator-initiated trip (operator authority preserved)
- without a fresh beat the gap keeps growing and entries stay parked (fail-closed)
- integration trace over a realistic timeline: every `STALLED` observation parks entries,
  a fresh heartbeat recovers

## Network / signed / execution evidence

- Network calls: NONE. Pure offline measurement.
- Signed calls: NONE.
- Orders / positions / fills / fees / funding / PnL: NONE. No exchange interaction.
- Protection: the `heartbeat` breaker trips and parks new entries; recovery verified via
  a fresh heartbeat clearing the monitor's own trip.
- Reconciliation: N/A for this unit (no venue state involved).

## Limitations (honest)

- This monitor proves *liveness*, not *correctness*. A runtime that completes cycles but
  computes wrong decisions still beats the heartbeat. Pair with the flat-line variation
  monitor (`src/health/variation.py`) and ledger-driven disposition checks.
- The simulation uses an injected monotonic clock; production wiring must feed real cycle
  completion timestamps from the orchestrator.
- The `auto_recovery` actor is trusted only because a heartbeat is a *verified* completed
  cycle observed by the runtime monitor; it is not a model-supplied signal and cannot be
  injected by the model.
- 495 tests pass, but several are heavy evaluation/data tests (209s total); runtime health
  itself is pure logic and isolated from that cost.

## Deterministic baseline / promotion gate

Phase 6 bounded LLM selection and all promotion actions remain blocked by the negative
deterministic baseline. This unit is unblocked research (runtime health) and does not
change the promotion gate.
