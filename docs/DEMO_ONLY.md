# Demo-only credential boundary

This standalone project accepts only demo/testnet configuration.

Required runtime invariants:

```text
mode: testnet
product_type: SUSDT-FUTURES
dry_run: true
withdrawals_enabled: false
```

The existing `/opt/bots/bitget-listener` service is configured separately and currently uses the live product type `USDT-FUTURES` with `PAPER=0`. Its credentials must not be copied into this project.

To proceed with signed demo calls later, create a separate Bitget demo API credential or a venue credential explicitly documented by Bitget as demo-only. Store it only in a local ignored environment file for this standalone project. Never paste it into chat or commit it.

The application must reject:

- `USDT-FUTURES`
- production REST/WS endpoints
- `mode=live`
- `dry_run=false`
- withdrawal methods

No credential has been imported or used by this project.
