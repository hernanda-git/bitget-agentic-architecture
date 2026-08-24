# Operations and Observability

## Required health dimensions

```text
provider: healthy | degraded | parked
market_data: fresh | stale | inconsistent
policy: loaded version and hash
execution: healthy | degraded
reconciliation: in_sync | drifted
protection: verified | missing | unknown
risk: armed | parked | kill_switch
mode: shadow | paper | testnet | live
```

## Metrics

- agent decisions per hour
- provider latency p50/p95/p99
- provider error and timeout rate
- schema rejection rate
- policy rejection rate by reason
- orders submitted and acknowledged
- fill latency
- realized and unrealized PnL from venue data
- fees and funding costs
- exposure by symbol and side
- protection verification age
- reconciliation drift count
- rate-limit breaker trips
- kill-switch state changes

## Required trace fields

Every agent cycle must include:

```text
trace_id
cycle_id
market_snapshot_id
market_snapshot_hash
context_hash
provider
model
prompt_version
schema_version
decision_json_hash
policy_version
policy_disposition
intent_id
venue_order_id
fill_ids
position_snapshot_id
protection_snapshot_id
created_at_asia_jakarta
```

## Alerts

Immediate:

- protection missing or stale
- venue/local position drift
- liquidation price on the wrong side of stop
- rate-limit breaker open
- provider circuit breaker open
- daily loss breaker
- unexpected transfer or withdrawal event
- process restart while position open

Periodic:

- flat-line agent decisions
- excessive `HOLD`
- repeated same-symbol rejection
- response distribution drift
- strategy PnL net of all fees

## Data retention

Keep raw provider response, normalized decision, policy result, venue response, and reconciliation result. Redact credentials and sensitive headers. Use Asia/Jakarta for displayed timestamps, while storing canonical UTC internally if needed.
