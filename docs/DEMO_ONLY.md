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

## F3 signed demo adapter gate

`src/execution/bitget_demo.py` is the only typed signed execution adapter. It is
separate from the offline paper and shadow runners. It accepts only an explicitly
allow-listed demo REST host, `SUSDT-FUTURES`, and `dry_run=true`. It rejects
`USDT-FUTURES`, production REST hosts such as `api.bitget.com`, `mode=live`,
`dry_run=false`, transfers, withdrawals, leverage mutation, and paths outside its
fixed order/read-back allow-list.

The adapter performs no HTTP request, including read-only requests, unless the
process environment contains this exact gate:

```text
DEMO_EXECUTION_CONFIRM=1
```

Example wiring with an injected transport (tests should always use
`httpx.MockTransport`):

```python
from src.execution.bitget_demo import BitgetDemoAdapter

adapter = BitgetDemoAdapter(
    base_url="https://demo-api.bitget.com",
    api_key=os.environ["BITGET_API_KEY"],
    api_secret=os.environ["BITGET_API_SECRET"],
    passphrase=os.environ["BITGET_PASSPHRASE"],
    product_type="SUSDT-FUTURES",
    mode="demo",
    dry_run=True,
)
result = adapter.execute({
    "symbol": "BTCUSDT", "side": "buy", "size": "1",
    "orderType": "market", "marginMode": "crossed", "marginCoin": "SUSDT",
})
```

`execute` derives a deterministic client ID, submits the order, reads the order
back, reads fills, reads positions, and returns a reconciliation result. Missing
stop-loss or take-profit evidence produces `PARKED_PROTECTION_MISSING` and never
reports a protected execution. The adapter has no transfer, withdrawal, or
leverage methods. Do not run this example casually, and never place credentials in
source control, chat, `/opt`, or test fixtures. Tests use mocked transport only and
place no order.

## Offline autonomous runners

`python scripts/run_autonomous_paper.py --mode paper --cycles 2 --symbols BTCUSDT`
uses only `FakeProvider`, `FakeExchange`, and a durable local SQLite ledger. It writes
paired `reports/run-<id>.json` and `.md` artifacts. A run fails closed with a nonzero
exit status when integrity checks fail or fake positions remain open. Use
`--scenario enter` only to exercise that failure gate.

`python scripts/run_autonomous_shadow.py --cycles 2 --symbols BTCUSDT` is observation-only
and uses fixture public observations. It reports zero network calls, zero signed calls,
and zero orders. Neither runner supports live or signed demo execution.
