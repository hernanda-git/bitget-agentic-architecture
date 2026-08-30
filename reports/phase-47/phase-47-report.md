# Phase 47 — Observability interface for the autonomous worker (TDD + mutation-verified)

**Date:** 2026-08-30
**Author:** valarion (42990222+hernanda-git@users.noreply.github.com)
**Discipline:** TDD + mutation-verified, fail-closed, offline, no signed/order calls.

## Summary

The user asked for a detailed, read-only interface to *see everything* about the
autonomous worker — every process and every piece of information, in detail. Until
now the heartbeat only delivered a concise markdown report to Telegram; there was
no live, browsable, machine-readable view of state, history, git, the factor
ontology, the resource guard, or the phase reports.

This phase adds a read-only observability surface:
- `scripts/heartbeat_status.py` — records each tick (append-only JSONL history +
  `last.json` snapshot) and assembles a status projection (git, latest tick,
  history, phase reports, factor-ontology coverage, resource guard, next scheduled
  run, hard constraints). Fail-closed: missing artifacts are reported as absent,
  never invented.
- `scripts/ui_server.py` — new `/api/heartbeat` endpoint (added alongside the
  existing read-only `/api/state`, `/api/health`); serves from `ui/` and rejects
  POST/PUT/DELETE with 405.
- `ui/heartbeat.html` — detailed auto-refreshing dashboard (polls `/api/heartbeat`
  every 10s): live tick status, git/repo, schedule + honesty gate, resource guard,
  factor-ontology coverage (with unrepresented categories flagged), latest phase
  report, full tick history table, and the raw JSON payload.
- The cron job prompt (`d4a8919dc60c`) now persists a tick record every run via
  `scripts.heartbeat_status.record_tick`, so the dashboard stays live. Phase 45 and
  46 records were backfilled from their real commit metadata.

## Changes

- Create `scripts/heartbeat_status.py` (record_tick, load_history, assemble_status,
  derive_next_run, git/phase/ontology/resource-guard readers).
- Create `tests/test_heartbeat_status.py` (5 tests).
- Modify `scripts/ui_server.py` — import + `/api/heartbeat` route.
- Create `ui/heartbeat.html`.
- Update cron job `d4a8919dc60c` prompt to persist a tick record each tick.
- Backfilled `data/heartbeat/last.json` + `ticks.jsonl` with real Phase 45/46 rows.

## Verification

- `python -m compileall -q src scripts` → clean.
- `tests/test_heartbeat_status.py` → **5 passed**.
- **Mutation check:** dropping the `ticks.jsonl` history write in `record_tick`
  flips `test_record_tick_appends_without_clobbering` RED, then reverted.
- **Secret scan (contents):** only benign hits — a docstring in
  `heartbeat_status.py` ("No secrets, no /opt/bots/bitget-listener…") and the
  negative-assertion test that verifies those strings are *absent*. No credentials,
  no live paths in any changed code.
- `/opt/bots/bitget-listener` referenced only in documentation/guard prose and the
  negative test — never in executable heartbeat code paths.
- `assemble_status` output verified to contain no `api_key`/`secret`/`token` and no
  `/opt/bots/bitget-listener` (asserted in `test_assemble_status_never_exposes_secrets_or_opt_bots`).
- Endpoint smoke: `assemble_status(DEFAULT_STATE_DIR)` returns all required keys,
  `history` len 2 after backfill, `git.commit` truthful, `next_scheduled_run`
  resolves to the next 6h boundary (18:00Z).

## Honest status

The deterministic baseline remains **negative → promotion blocked** (no live/edge
claim). This phase is an observability addition only — it changes nothing about the
trading/research logic, the fail-closed honesty gate, or the shadow-only posture.
The dashboard is read-only and makes no calls; it surfaces facts already true in the
repo. Three factor-ontology categories remain unrepresented (visible on the
dashboard, not hidden).

## How to view

Start the server: `python scripts/ui_server.py` (binds 127.0.0.1:8765). Open
`http://127.0.0.1:8765/heartbeat.html`. On a remote box, reach it via an SSH tunnel
(`ssh -L 8765:127.0.0.1:8765 <host>`) and browse `http://localhost:8765/heartbeat.html`.
