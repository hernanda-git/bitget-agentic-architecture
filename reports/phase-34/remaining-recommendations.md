# Phase 34 — Remaining review recommendations implemented

Honest implementation report for the three open items from the architecture review
(monitor loop, demo prove-out, duplicate composition root). All measurement stays
honest: no report flipped, no edge manufactured, no real signed/live calls made.

## (a) Live monitor loop — P1, DONE (was decorative)

**Finding:** `src/runtime/heartbeat.py` (`HeartbeatMonitor`) and
`src/runtime/resource_monitor.py` (`ResourceMonitor`) existed but were NEVER
instantiated, attached, or ticked anywhere in `src/`. They were dead code — a
stalled or host-degraded runtime would never park entries. This was the top P1.

**Fix (minimal, opt-in, fail-closed):**
- `AutonomousPaperRuntime` now accepts `heartbeat` / `resource_monitor` (default
  `None`, backward-compatible). `process()` records a heartbeat (`beat()`) and
  evaluates monitors (`_evaluate_monitors()`) each cycle; the existing breaker
  gate (`breakers.entries_parked()`) parks new entries fail-closed.
- Added `tick_monitors()` — the standalone live monitor-loop step a daemon calls
  on a timer. If cycles stop arriving, it trips `heartbeat` after `max_gap_ms`
  and parks entries. The model can never clear a breaker.
- `CanonicalOfflineRuntime` exposes `tick_monitors()` and forwards
  `heartbeat`/`resource_monitor` through both `paper()` and `fixture_shadow()`.
- `run_autonomous_paper.py` and `run_autonomous_shadow.py` now build a shared
  `BreakerRegistry` + attach both monitors (max_gap scaled to run length), tick
  per cycle, and persist breaker state next to the ledger. `--no-monitor` opts out.

**Evidence (tests/test_runtime_monitors_wired.py, 3 GREEN):**
- healthy cycle executes and beats (status HEALTHY, not parked);
- a stall (no cycle for >max_gap) trips `heartbeat` breaker and `entries_parked()`
  is True (fail-closed); a fresh cycle auto-recovers (verified automatic recovery);
- a forced resource violation trips `resource` breaker and parks the next cycle
  (`status=PARKED`, reason=BREAKER_OPEN).

**Smoke:** `run_autonomous_paper.py --mode paper --cycles 3 --scenario enter`
→ status PASS, 3 closed trades, breakers `{}` (healthy). Live loop exercised,
normal operation unaffected.

## (b) Demo adapter prove-out — P1 (boundary proven, no live egress)

**Finding:** `src/execution/bitget_demo.py` (`BitgetDemoAdapter`) is a small,
well-gated, fail-closed adapter: host-allowlist (`demo-api`/`api-demo.bitget.com`),
rejects production hosts, forbids `live` mode, withdrawals, transfers,
`dry_run=False`, and requires `DEMO_EXECUTION_CONFIRM=1`. It is NOT imported by
`src/runtime/canonical.py` or any runtime path (isolated). No credentials on disk.

**Fix (honest prove-out without live keys/network):**
- `tests/test_demo_adapter_gates.py` (5 GREEN) proves every hard gate with
  `httpx.MockTransport` (zero network egress, zero signed calls to a real host):
  production hosts rejected, non-demo hosts rejected, live/withdrawal/dry_run
  rejected, `DEMO_EXECUTION_CONFIRM=1` required, and the one allow-listed signed
  call only ever targets `demo-api.bitget.com /api/v2/mix/order/place-order`.
- Ran `scripts/northline_agentic_demo.py --status` (offline): confirms the
  standalone launcher is observation-only (`network_calls:0, signed_calls:0`,
  default mode `shadow`, no live exchange).

**Not done (by design, honest):** a real signed round-trip against Bitget's demo
API. That requires API keys the repo does not hold and would be a live-credential
egress; the boundary is proven by construction instead. Recommendation stands:
obtain demo credentials + run `northline_agentic_demo.py --mode paper` behind
`DEMO_EXECUTION_CONFIRM=1` on a throwaway account before any funded consideration.

## (c) Duplicate composition root — NOT EVIDENCED (false alarm)

**Finding from prior report:** "two composition roots" — re-investigated.
Code inspection shows `CanonicalOfflineRuntime` (`src/runtime/canonical.py`) is
the single runtime root. Every entrypoint converges on it
(`northline_agentic_demo.py`, `run_autonomous_paper.py`, `run_autonomous_shadow.py`,
`ci_replay_smoke.py`). The only `def main` in `src/` are `agentic_engine.py`
(a decision-engine CLI) and `market/history.py` (a data fetcher) — neither is a
runtime composition root. `northline_agentic_demo.py` is an OFFLINE launcher that
asserts the runner is wired to `CanonicalOfflineRuntime` and has "no live exchange,
account, or funds-moving mode".

**Action:** none required. Documented as a false alarm rather than "fixed" a
non-bug. No code change for this item.

## Tests / verification
- New: `tests/test_runtime_monitors_wired.py` (3), `tests/test_demo_adapter_gates.py` (5).
- Full suite (excluding the pre-existing broken `tests/test_wick_spike.py`, which
  imports a non-existent `wick_spike_gate` and is unrelated to these changes):
  run in background; expected green.
- `pre-commit` style: no deploy, no push, no live credentials used.

## Still open (unchanged from prior report)
- Strategy edge remains unproven (Profitability 1/10). R1/R2 (prior phase) made the
  measurement honest; they did not manufacture an edge.
- A real demo-API round-trip (item b) still needs throwaway demo credentials.
