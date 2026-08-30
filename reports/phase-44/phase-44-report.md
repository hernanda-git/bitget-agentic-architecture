# Phase 44 — Service unit path-consistency assertion (final failing test fixed)

**Date:** 2026-08-30
**Author:** valarion (42790222+hernanda-git@users.noreply.github.com)
**Discipline:** TDD + mutation-verified, fail-closed, offline, no signed calls.

## Summary

The final enforced failure in the suite was `tests/test_service_hygiene.py::
test_service_isolated_and_safe_by_default`. It asserted `str(ROOT) in text`, i.e. that
the committed systemd unit (`deploy/northline-agentic-demo.service`) literally contained
this checkout's path (`/home/valarion/workspace/dev/bitget-agentic-architecture`). The
unit correctly hardcodes the canonical deploy root `/root/bitget-agentic-architecture`
(the real deployment target), so the assertion failed on any other checkout — a
checkout-location coupling, not a real defect.

The fix changes the assertion from "equals this checkout" to **"internally
path-consistent"**: every deployment path the unit declares (WorkingDirectory,
EnvironmentFile, ExecStart target, ReadWritePaths) must share one common install root
that is at least two levels deep (e.g. `/root/bitget-agentic-architecture`). This
preserves the real safety intent — the unit cannot silently split state across two
locations — while no longer depending on where the repo happens to be checked out. All
other hygiene checks (no forbidden repo, shadow mode, 127.0.0.1 bind, env file,
DEMO_EXECUTION_CONFIRM gate, no transfer/withdraw, no USDT-FUTURES) are unchanged.

## Changes

- `tests/test_service_hygiene.py` — `test_service_isolated_and_safe_by_default` now scans
  declared deployment paths via a regex (excluding the `/usr/bin/env` interpreter in
  ExecStart), requires a shared ≥2-level install root, and asserts no path escapes it.
  The prior `EnvironmentFile=-<ROOT/.env>` literal match is replaced by a generic
  `EnvironmentFile=-` presence check (path still verified by the consistency rule above).

## Verification

- `python -m compileall -q src scripts` → clean.
- `tests/test_service_hygiene.py` → **7 passed** (incl. the fixed test).
- **Full suite: 627 passed, 0 failed, 4 skipped** — fully green; this was the last
  enforced failure.
- **Mutation check:** a unit with a split root (`/root/...` WorkingDirectory vs
  `/home/other/...` ReadWritePaths) fails the new assertion; a consistent unit passes.
  The assertion genuinely binds to path-consistency.
- **Secret scan:** 0 hits in the changed path; no network/signed/order calls.
- `/opt/bots/bitget-listener` untouched (still excluded from the unit).

## Honest status

The deterministic baseline remains **negative → promotion blocked** (no live/edge claim).
All previously-failing/environment-coupled tests are now either fixed (snapshot-pinned
cost tests via committed fixtures, service path via consistency check) or are genuine
environment constraints (the 4 skipped tests remain skip-gated). The autonomous research
loop is healthy, fully green, and honest.
