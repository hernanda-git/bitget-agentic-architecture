# public-shadow report

- Status: `PUBLIC_SHADOW_COMPLETE`
- Cycles: `100` requested, `100` completed, `100` terminal
- Terminal statuses: `HOLD=100`
- Provider calls/failures: `0/0`
- Schema/policy rejections: `0/0`
- HOLD/candidate rates: `1.0000` / `0.0000`
- Simulated entries/exits: `0/0`
- Net PnL after costs: `0.0`

## Distributions

- Freshness: `{'count': 100, 'min': 189, 'max': 425, 'mean': 216.24, 'p50': 211}`
- Spread: `{'count': 100, 'min': 0.01244908324842256, 'max': 0.012455549259308439, 'mean': 0.012452210470533617, 'p50': 0.012451842499859391}`
- Decision latency: `{'count': 100, 'min': 592.58679789491, 'max': 892.2973431181163, 'mean': 650.6960365641862, 'p50': 639.9039749521762}`

## Validation outcome

The earlier degraded run exposed a validation bug, not bad public data: legitimate positive Bitget `markPrice`/`lastPr` values can sit outside the bid-ask interval. The repair validates positive bid/ask/mark values and `bid <= ask` independently, without requiring mark to be inside the spread. Regression coverage is in `test_ticker_validation_accepts_positive_mark_outside_spread_and_rejects_invalid_values`.

## Safety

- Network calls: `400`
- Signed calls: `0`
- Orders placed: `0`
- Limitations: `['public market observations only', 'no provider selection or execution', 'PnL is zero because no simulated positions were opened']`
