# Threat Model

## Assets to protect

- Bitget API key, secret, and passphrase
- Exchange balance and open positions
- Position protection and liquidation distance
- Ledger integrity
- Agent prompt and policy integrity
- Operator ability to halt new trading

## Primary threats and controls

| Threat | Control | Failure result |
|---|---|---|
| Prompt injection in market/news text | Treat all external text as data; no tool instructions from content | Ignore content or `HOLD` |
| LLM hallucinated symbol or price | Symbol allowlist, live ticker cross-check, price age gate | Reject |
| LLM direction flip | Structured decision plus semantic validation and confidence floor | Reject |
| Provider outage or quota exhaustion | Timeout, bounded retry, provider circuit breaker | `NO_DECISION`, no new order |
| Prompt/model drift | Versioned prompt, model, schema, response hash | Audit and rollback |
| Excessive leverage | Fixed policy cap and venue cap | Reject |
| Daily loss or drawdown breach | Live equity-based breaker | Park new entries |
| Duplicate decision/order | Deterministic decision ID and client order ID | Skip duplicate |
| Bitget API accepts but state differs | Venue read-back and reconciliation | Park and alert |
| Missing SL/TP | Protection verification before considering position healthy | Park, close according to emergency policy |
| WebSocket silence | Freshness watchdog and REST fallback with timeout | Park |
| Rate limit / ban | Per-category token buckets and 429 breaker | Park |
| Secret leakage in logs/context | Redaction and provider boundary tests | Fail deployment |
| Agent edits its own constraints | Policy outside agent tools, immutable at runtime | Reject |
| Wallet withdrawal abuse | No withdrawal method in execution interface | Impossible through agent path |
| Local state corruption | Append-only event store and venue reconciliation | Rebuild from venue |
| Smart-contract or exchange outage | Venue health gate and emergency exposure rules | No new entries |

## No-human-per-trade policy

The system is fully autonomous during normal operation. Human interaction is limited to out-of-band governance:

- initial configuration
- deployment approval
- funding
- changing risk policy
- rotating keys
- emergency kill switch

These are not trade approvals. The agent remains responsible for normal enter, manage, and exit decisions.

## Kill switch behavior

The kill switch is outside the LLM process. It must:

1. Stop new entries immediately.
2. Continue reconciliation.
3. Continue protective monitoring.
4. Preserve the ledger.
5. Require explicit operator action to resume.

A provider cannot clear the kill switch.

## Residual risks

- A valid model output can still lose money.
- A venue can fail after an order is submitted.
- Protection can fail despite a successful API response.
- Market gaps can exceed stop assumptions.
- Model behavior can degrade without a schema violation.
- Backtests can overfit and do not prove future profitability.

The system must expose these risks rather than convert them into a false confidence score.
