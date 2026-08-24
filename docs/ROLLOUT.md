# Autonomous Rollout Gates

## Gate 0, architecture and security

- No secrets in repository.
- Provider adapter has no exchange signing access.
- Execution adapter has no withdrawal method.
- Policy is loaded outside agent context.
- Decision and intent schemas validate.
- Kill switch is tested.

## Gate 1, shadow

Duration: minimum 7 days or 1,000 decision cycles, whichever is longer.

Requirements:

- Real Bitget market data.
- Zero orders.
- Every cycle has a terminal disposition.
- Provider uptime, latency, malformed JSON, and rejection rate measured.
- Agent decisions compared against deterministic baselines.
- No silent exceptions.

## Gate 2, paper

Requirements:

- Fake exchange adapter and replay data.
- Full order, fill, fee, protection, and reconciliation simulation.
- Forced failures: timeout, stale mark, wrong symbol, duplicate order, missing SL/TP, 429, restart.
- Ledger PnL must reconcile against the fake venue.

## Gate 3, testnet

Requirements:

- Real Bitget testnet or demo product only.
- No production API credentials in the process.
- Read-back verification for every order and protection action.
- Restart with open positions and recover without naked exposure.
- Kill switch tested while an order and position are active.

## Gate 4, micro-live

Requirements:

- Explicit operator deployment action, not per-trade approval.
- Smallest practical account size.
- One symbol or a measured tradability set.
- `max_concurrent=1` initially.
- Small fixed notional cap.
- Daily loss circuit breaker smaller than the funding amount.
- Real balance, fee, fill, liquidation, and protection fields read from Bitget.
- No claim that the bot is protected until venue or bot-side protection is read back.

## Gate 5, scale

Only after stable micro-live evidence:

- Increase symbols gradually.
- Increase concurrency gradually.
- Re-measure minimum notional after balance changes.
- Review expectancy net of fees and funding.
- Never scale from model confidence alone.

## Rollback

Rollback means:

1. Set new entries to `PARKED`.
2. Keep reconciliation and protection monitor alive.
3. Reconcile all live positions.
4. Close only according to the emergency policy and verified venue state.
5. Preserve logs and decision traces.
6. Revert provider, prompt, or policy version.

A code rollback must not erase ledger events or silently reopen trading.
