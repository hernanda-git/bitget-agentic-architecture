# Per-liquidity-tier cost-stress envelope (observed spread)

Table: `reports/phase-36/orderbook_calibration.json`
Symbols replayed: 28 | Snapshots/symbol: 300
Unknown (no observed spread): ['AAVEUSDT', 'APTUSDT', 'ARBUSDT', 'ATOMUSDT', 'BCHUSDT', 'BNBUSDT', 'DOGEUSDT', 'DOTUSDT', 'ETCUSDT', 'FILUSDT', 'INJUSDT', 'LINKUSDT', 'LTCUSDT', 'OPUSDT', 'TINYUSDT', 'TRXUSDT', 'UNIUSDT', 'XLMUSDT']

- selection_blocked: True
- promotion_blocked: True

## Tiers

| Tier | Symbols | n_cells | min_net | median_net | max_net | any_profitable | all_blocked |
|------|---------|---------|---------|------------|---------|----------------|-------------|
| TIER_MODERATE | XRPUSDT | 8 | -0.1187 | -0.1092 | -0.1025 | False | True |
| TIER_TIGHT | BTCUSDT, ETHUSDT, SOLUSDT | 40 | -2622.5875 | -61.8157 | 954.4047 | True | False |
| TIER_WIDE | ADAUSDT, AVAXUSDT, NEARUSDT, SUIUSDT | 32 | -0.1320 | -0.0231 | -0.0014 | False | True |

**Honest reading:** every tier here is reported under the blocked gate. The table calibrates the *minimum* quoted spread; actual fills at size are worse. No promotion is authorized while the deterministic baseline is negative.