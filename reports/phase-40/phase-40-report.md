# Phase 40 — Realistic Bitget funding-settlement accrual model (TDD + mutation-verified)

**Generated (WIB / Asia/Jakarta):** 2026-08-29 (cron autonomous run)
**Author identity:** hernanda-git (42990222+hernanda-git@users.noreply.github.com)
**Mode:** offline pure-model work + offline unit tests (zero network egress, zero orders)
**Phase 6 (bounded LLM selection) status:** BLOCKED (unchanged) — this phase is a cost-accuracy hardening stream and does not touch the deterministic gate. No promotion/selection/winner flag is emitted or flipped.

## Scope and why it is unblocked

The cron mandate lists `realistic cost/funding/slippage stress` and `strategy attribution` as unblocked streams. The previous cost model applied funding at every replay bar (a per-bar proxy), which overstates funding by roughly the bar count for sub-8h holds and is not how Bitget bills. Bitget USDT perpetuals settle funding every 8 hours at 00:00 / 08:00 / 16:00 UTC. Every settlement boundary is an exact multiple of `8h` in epoch milliseconds (`k * 8h_ms`) because the Unix epoch (1970-01-01 00:00:00 UTC) is itself a settlement boundary, so settlement membership is a single modulus check and the calendar is trivially reproducible.

This phase adds a pure, deterministic, offline funding-accrual model (`src/evaluation/funding_model.py`) that computes funding only at the real 8h settlement timestamps strictly inside a position's open interval, direction-aware (long pays / receives opposite to short), using the per-settlement rate (already the 8h rate, e.g. `0.0001`), never a per-bar rate. It also exposes a reconciliation helper (`reconcile_funding_legs`) so the ledger can prove the sum of per-settlement legs equals the reported position funding, closing the reconciliation loop on the realistic model.

The implementation and its test suite were authored in a prior interrupted session but left untracked. This run verifies them: confirms GREEN, mutation-verifies the assertions bind to behavior, documents them, and commits. (The RED step for these files occurred in the prior session; this run proves the suite is not decorative via a fresh mutation check.)

## TDD cycle (strict)

### A. Settlement calendar (`is_settlement_timestamp`, `settlement_timestamps_in_range`)
- The test suite (`tests/test_funding_model.py`) asserts epoch + 8h/16h/24h boundaries are settlements, non-boundaries are not, and the range helper is exclusive-start / inclusive-end with no settlement strictly inside a sub-8h window.
- **GREEN (verified this run):** `pytest tests/test_funding_model.py -q` -> `9 passed`.
- **Mutation check (build-verification skill):** inverted the direction guard in `position_funding` (`if side == "BUY":` -> `if side == "SELL":`) so a long with a positive rate is treated as a short. `tests/test_funding_model.py::test_long_pays_positive_rate_receives_negative` went RED (`assert -0.03 == 0.03`). Reverted -> GREEN. The assertion genuinely binds to the direction logic.

### B. Direction-aware accrual (`position_funding`, `FundingLeg`)
- Tests assert: long pays a positive rate and receives a negative one; short is the mirror; funding only accrues at settlements (a 57 one-minute-bar hold crossing no settlement pays exactly 0, whereas a per-bar proxy would have charged 57 times); and `reconcile_funding_legs(legs)` equals the returned net.
- **GREEN (verified this run):** 9 passed.
- **Bad-side guard:** `position_funding("HOLD", ...)` raises `ValueError` (test `test_position_funding_rejects_bad_side`).
- **Dataclass contract:** `FundingLeg` carries all fields (`ts_ms, rate, mark, paid, received`) — test `test_funding_leg_is_dataclass_with_all_fields`.

## What this run added / changed
- `src/evaluation/funding_model.py` — NEW: `EIGHT_HOURS_MS`, `FundingLeg`, `is_settlement_timestamp`, `settlement_timestamps_in_range`, `position_funding`, `reconcile_funding_legs`. Pure measurement + reconciliation. No network, credentials, signed calls, or orders.
- `tests/test_funding_model.py` — NEW: 9 TDD tests covering the calendar, direction-aware accrual, the per-bar-vs-settlement distinction, reconciliation, and the bad-side guard.
- `reports/phase-40/phase-40-report.md` — this report.

## Raw tests (executed this run)
```text
# GREEN (the model + tests were authored in a prior session; verified this run)
pytest tests/test_funding_model.py -q
    -> 9 passed
# compileall
python3 -m compileall -q src tests
    -> exit 0 (clean)
# mutation check (temporary, reverted):
#   position_funding direction guard BUY -> SELL :
#     test_long_pays_positive_rate_receives_negative -> 1 failed (assert -0.03 == 0.03)
#   reverted -> 9 passed
```

## Offline runner evidence (no egress, pure function)
Driven through pure functions with synthetic callables (`mark_at`, `rate_at`):
- `is_settlement_timestamp(0)` / `(8h_ms)` / `(16h_ms)` / `(24h_ms)` -> True; `(1h_ms)`, `(4h_ms)`, `(8h_ms-1)` -> False.
- A long of qty 1.0, mark 100, rate 0.0001 over `(0, 24h]` -> 3 legs, net = `0.03` (3 settlements * 1 * 100 * 0.0001), all paid > 0. Same with rate `-0.0001` -> net = `-0.03` (received). Short is the mirror.
- A position over 57 one-minute bars (< 8h) -> `legs == []`, `net == 0.0` (realistic; a per-bar proxy would have charged 57 times).
- `reconcile_funding_legs(legs)` == returned net for every case (reconciliation loop closed).

## Network calls
- **0 network calls this run.** All inputs are synthetic callables / fixtures. No `GET`, no authenticated, signed, or account endpoints were touched.

## Signed calls / orders / positions
- **Signed calls: 0.** Orders: 0. Positions: 0 (open or closed by this phase). No credentials, demo keys, or live keys were used. No signed exchange calls, transfers, withdrawals, or funded execution occurred. Egress: none.

## Trades / fees / funding / PnL
- **Trades executed by this phase: 0.** Fees: 0. Funding: 0 (this is a pure accrual model; it does not trade). PnL: 0 realized. The model *measures* realistic funding; it does not alter the deterministic baseline's sign.

## Protection / reconciliation
- The model adds a reconciliation helper (`reconcile_funding_legs`) so the ledger can prove per-settlement legs sum to the reported position funding. No protection or live reconciliation path was altered. Wiring this model into the replay/paper cost path is intentionally deferred to Phase 41 (a separate, scoped change) so the mutation-verified baseline here stays isolated and reviewable.

## Limitations (honest)
- This model is pure measurement. It does not yet replace the per-bar proxy inside `FakeExchange.apply_market_event` / `baseline.py`; that wiring is the explicit next step (Phase 41). Until then, synthetic short-series baselines still overstate funding per-bar.
- The model assumes the venue bills exactly at 8h UTC multiples. This is correct for Bitget USDT perpetuals; other venues with different cadences would need a parametrized settlement interval (out of scope here).
- Funding rate is supplied by the caller (`rate_at`); the model does not fetch or infer rates. Real-data replay supplies the observed per-settlement rate from the public funding history (no auth).

## Phase 6 promotion gate
- **Still BLOCKED.** This phase is a cost-accuracy hardening change only. The deterministic baseline remains negative; no promotion action was taken and none is authorized while the baseline is negative.

## Commit / push
- New/changed: `src/evaluation/funding_model.py`, `tests/test_funding_model.py`, `reports/phase-40/phase-40-report.md`.
- Git identity verified: `user.name=𝕧𝕒𝕝𝕒𝕣𝕚𝕠𝕟`, `user.email=42990222+hernanda-git@users.noreply.github.com` (matches `gh api`).
- Secret scan: `.env` is git-ignored; content scan over tracked + new text found **0 secret hits**. Verified repeatable, network-free, secret-free command: `pytest tests/test_funding_model.py -q`.
- **Resource guard (this run):** `ok=true`, disk 45.8% used / 31.6 GB free, swap 49.8% used, 49.9% inodes free, 1220 MB memory available. Heavy work proceeded; no exhaustion.
