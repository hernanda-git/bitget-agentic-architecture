# Phase 41 — Wire realistic 8h funding-accrual model into the paper exchange (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-30 (autonomous continuation run, Hermes)
**Author identity:** 𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟 (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline pure-model + offline unit tests (zero network egress, zero orders)
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase is a cost-accuracy
hardening stream and does not touch the deterministic promotion gate. No promotion/selection/winner
flag is emitted or flipped. The deterministic baseline remains negative; no promotion action taken.

## Scope and why it is the correct next step

Phase 40 shipped the pure, deterministic, settlement-accurate funding model
(`src/evaluation/funding_model.py`) but explicitly deferred wiring it into the replay/paper cost
path: *"Wiring this model into the replay/paper cost path is intentionally deferred to Phase 41 ...
Until then, synthetic short-series baselines still overstate funding per-bar."* This phase closes
that gap.

The previous (and still conservative) behavior charged funding on **every** `apply_market_event`
that carried a nonzero `funding_rate` (a per-bar proxy). Bitget USDT perpetuals settle funding only
at the 8h UTC boundaries (00:00 / 08:00 / 16:00), so the per-bar proxy overstates funding by ~the
bar count between settlements (e.g. ~480x for 1m bars vs 8h). This phase makes the exchange delegate
settlement-accurate accrual to the shared, mutation-verified model so the paper path matches how the
venue actually bills.

## Design (minimal, behavior-preserving)

- `src/evaluation/funding_model.py`: added `settlement_funding_leg(side, qty, mark, rate) ->
  (paid, received)` — the per-leg mirror of `position_funding`'s inner direction math, exposed so
  the exchange delegates every accrual to the same model instead of re-implementing the rule. Raises
  `ValueError` for an unknown side, exactly like `position_funding`.
- `src/execution/fake_exchange.py`: `apply_market_event` now branches on the event timestamp:
  - When `event.timestamp_ms` is an actual 8h settlement boundary (`is_settlement_timestamp`),
    accrual is delegated to the new `apply_funding_settlement` method, which calls
    `settlement_funding_leg` — one realistic leg, direction-aware, matching `position_funding`.
  - When the event timestamp is NOT a settlement boundary (synthetic fixtures whose bar timestamps
    are not settlement-aligned), it keeps the **conservative per-bar proxy** as a fail-closed upper
    bound. This preserves `real_funding=False` stress-path behavior and the existing per-bar tests.
- `src/market/history.py`: unchanged in semantics — a settlement rate is still attached to the first
  snapshot on/after each funding-record time (once per settlement, never per bar). For real history
  the settlement-time snapshot carries a `source_ts_ms` that IS an 8h boundary, so the exchange takes
  the model path automatically. (`HistoryDataset` funding timestamps are observed venue settlement
  times; the exchange-sided `is_settlement_timestamp` gate is the switch.)

## TDD cycle (strict)

1. Wrote failing/characterizing tests first:
   - `tests/test_funding_model.py::test_settlement_funding_leg_matches_position_funding_direction`
     (RED until `settlement_funding_leg` existed).
   - `tests/test_phase2_exchange.py::test_funding_accrues_one_realistic_leg_per_settlement`,
     `test_funding_non_settlement_event_uses_conservative_per_bar_proxy`,
     `test_funding_settlement_short_receives_positive_rate` (characterize the new branch).
2. Implemented the minimum code. Targeted run: `pytest tests/test_funding_model.py
   tests/test_phase2_exchange.py` -> **24 passed**.
3. Full suite run -> **611 passed, 5 failed, 11 skipped** (was 607 passed / 5 failed / 11 skipped).
   Net +4 tests, **zero new failures**.
4. Mutation verification (assertions bind to behavior):
   - MUT1: `settlement_funding_leg` direction guard — BUY `(0.01, 0.0)` vs SELL `(0.0, 0.01)` differ.
   - MUT2: exchange gating — non-settlement event accrues via proxy (0.01); a settlement event adds
     exactly one model leg (0.01). Both paths independent and observable.
   - MUT3: forcing `is_settlement_timestamp` to always-False routes everything through the proxy,
     proving the gate is the switch.

## Files created / modified

- `src/evaluation/funding_model.py` — NEW `settlement_funding_leg`.
- `src/execution/fake_exchange.py` — settlement-gated accrual + `apply_funding_settlement` +
  `_per_bar_funding` helper; imports `is_settlement_timestamp`, `settlement_funding_leg`.
- `src/market/history.py` — funding-attachment comment/semantics clarified (no behavior change).
- `tests/test_funding_model.py` — NEW `test_settlement_funding_leg_matches_position_funding_direction`.
- `tests/test_phase2_exchange.py` — NEW settlement-accrual + proxy-fallback + short-mirror tests.
- `reports/phase-41/phase-41-report.md` — this report.

## Raw tests (executed this run)

```text
python -m compileall -q src scripts
    -> exit 0 (clean)
python -m pytest tests/test_funding_model.py tests/test_phase2_exchange.py -q
    -> 24 passed
python -m pytest -q -p no:cacheprovider
    -> 611 passed, 5 failed, 11 skipped   (5 failures are pre-existing, environment-bound, see below)
```

## Network calls
- **0 network calls this run.** All inputs are synthetic fixtures / pure functions. No `GET`, no
  authenticated, signed, or account endpoints were touched.

## Signed calls / orders / positions
- **Signed calls: 0.** Orders: 0. Positions: 0. No credentials, demo keys, or live keys were used.
  No signed exchange calls, transfers, withdrawals, or funded execution occurred. Egress: none.

## Remaining failures (pre-existing, environment-bound, NOT caused by this phase)

1. `test_combined_stress.py::test_combined_stress_pipeline_invariant_on_real_dataset`
2. `test_cost_envelope.py::test_envelope_on_real_history_reports_full_block_and_envelope`
3. `test_cost_envelope_per_tier.py::test_cost_envelope_per_tier_real_history_blocked`
4. `test_cost_sensitivity.py::test_break_even_absent_on_real_history_even_at_zero_scalable_cost`
   - These four require the gitignored offline public-history corpus under `data/history/*.json`,
     which is never committed (`.gitignore` ignores `data/history/`). They fail with
     `FileNotFoundError: data/history/ETHUSDT_1m.json`. This is a data-availability matter on this
     machine, not a code regression. They were failing identically on the pre-edit baseline.
5. `test_service_hygiene.py::test_service_isolated_and_safe_by_default`
   - Asserts the deploy service file contains the repo root path; the committed service hardcodes
     `/root/bitget-agentic-architecture` while this checkout lives at
     `~/workspace/dev/bitget-agentic-architecture`, so the path assertion fails. Pre-existing and
     environment-specific; the service file itself is still safe-by-default (shadow mode, localhost,
     `DEMO_EXECUTION_CONFIRM` gated). Not touched by this phase.

## Limitations (honest)

- The exchange settlement gate keys off `MarketEvent.timestamp_ms`. In real-history replay the
  settlement-time snapshot carries a genuine 8h-boundary `source_ts_ms`, so the model path is taken
  automatically. Synthetic fixtures with arbitrary bar timestamps intentionally stay on the
  conservative per-bar proxy.
- `snapshots_from_dataset` attaches the observed settlement rate to the bar that crosses the
  funding record time (one charge per settlement), which is the documented pre-existing contract the
  evaluation tests pin. Real per-settlement accuracy is delivered by the exchange-side model
  delegation.
- This phase does not change the deterministic promotion gate or the negative baseline sign.

## Phase 6 promotion gate
- **Still BLOCKED.** This is a cost-accuracy hardening change only. The deterministic baseline
  remains negative; no promotion action was taken and none is authorized while the baseline is
  negative.

## Commit / push
- New/changed: `src/evaluation/funding_model.py`, `src/execution/fake_exchange.py`,
  `src/market/history.py`, `tests/test_funding_model.py`, `tests/test_phase2_exchange.py`,
  `reports/phase-41/phase-41-report.md`.
- Git identity verified: `user.name=𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟`, `user.email=42990222+hernanda-git@users.noreply.github.com`.
- Secret scan over tracked + new text found **0 secret hits** (only doc prose mentions "secret" and
  the untracked, gitignored `quarantine/demo-probes/*` read credentials from `os.environ`, no
  hardcoded values). `git check-ignore .env` -> `.env` is ignored. `git ls-files | grep .env` -> 0
  tracked.
- `.env` confirmed gitignored; no secrets committed.

## /opt/bots/bitget-listener
- **Unchanged.** This directory was not read, modified, restarted, deployed, or connected to. The
  integration boundary in `docs/INTEGRATION_BOUNDARY.md` is preserved.
