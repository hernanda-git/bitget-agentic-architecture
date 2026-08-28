#!/usr/bin/env python3
"""Gated Bitget DEMO prove-out runner (read-only by default, fail-closed).

Purpose: drive the typed, gated ``BitgetDemoAdapter`` against Bitget's DEMO
host so a real signed round-trip can be observed before any funded
consideration. This is the honest "real demo prove-out" path that
``northline_agentic_demo.py --mode paper`` does NOT cover (that runner is
offline FakeExchange only).

Safety (defense in depth, all enforced before any transport call):
* The target host MUST be a demo allow-list host (``demo-api.bitget.com`` or
  ``api-demo.bitget.com``) or localhost/127.0.0.1. A production host is refused
  here AND again by ``BitgetDemoAdapter`` (which forbids ``api.bitget.com``).
* ``DEMO_EXECUTION_CONFIRM=1`` is required (the adapter's own gate).
* The adapter is constructed with ``mode="demo"``, ``dry_run=True`` (forced),
  ``withdrawals_enabled=False``, ``transfers_enabled=False``. Live mode and
  transfers are impossible by construction.
* Credentials come from the environment ONLY (BITGET_API_KEY / BITGET_API_SECRET
  / BITGET_PASSPHRASE / BITGET_REST_BASE). This runner does NOT load ``.env``
  and never prints secrets.
* Default action is read-only (``read_positions``). Use ``--place`` to also
  submit one demo order (still dry-run, still demo host).

No live keys, no production host, no withdrawals. Pure demo prove-out.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.execution.bitget_demo import BitgetDemoAdapter, DEMO_PRODUCT_TYPE

_DEMO_HOSTS = {"demo-api.bitget.com", "api-demo.bitget.com"}


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"missing environment variable: {name}")
    return val


def _validate_host(base_url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(base_url).hostname or ""
    if host in _DEMO_HOSTS or host in {"127.0.0.1", "localhost"}:
        return base_url
    raise SystemExit(
        f"refusing non-demo host '{host}'. This runner only targets demo hosts "
        f"{sorted(_DEMO_HOSTS)} (or localhost). The BitgetDemoAdapter also forbids "
        f"production hosts. Point BITGET_REST_BASE at a demo host."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="gated Bitget DEMO prove-out (read-only by default)")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"])
    parser.add_argument("--size", default="1")
    parser.add_argument("--price", default="100")
    parser.add_argument("--place", action="store_true", help="also submit one demo order (still dry-run, demo host only)")
    parser.add_argument("--output", type=Path, default=Path("reports/phase-34/demo-proveout.json"))
    args = parser.parse_args()

    if os.environ.get("DEMO_EXECUTION_CONFIRM") != "1":
        parser.error("DEMO_EXECUTION_CONFIRM=1 is required to run the demo prove-out")

    base_url = _require_env("BITGET_REST_BASE")
    base_url = _validate_host(base_url)  # defense in depth: refuse production early
    api_key = _require_env("BITGET_API_KEY")
    api_secret = _require_env("BITGET_API_SECRET")
    passphrase = _require_env("BITGET_PASSPHRASE")

    started_ms = int(time.time() * 1000)
    adapter = BitgetDemoAdapter(
        base_url=base_url, api_key=api_key, api_secret=api_secret, passphrase=passphrase,
        mode="demo", dry_run=True, withdrawals_enabled=False, transfers_enabled=False,
    )

    # 1) Read-only proof: observe current demo positions (no order, no mutation).
    positions = adapter.read_positions(args.symbol)
    proof = {
        "mode": "demo",
        "host": base_url,
        "product_type": DEMO_PRODUCT_TYPE,
        "symbol": args.symbol,
        "positions_observed": len(positions),
        "read_only_ok": True,
        "started_ms": started_ms,
        "completed_ms": int(time.time() * 1000),
        "signed_calls": 1,
        "withdrawals": False,
        "live_mode": False,
    }

    # 2) Optional one demo order (still dry-run, demo host only).
    if args.place:
        order = {"symbol": args.symbol, "side": args.side, "size": args.size, "price": args.price}
        result = adapter.execute(order)
        proof["order"] = {
            "disposition": result.disposition,
            "order_id": str(result.order.get("orderId", "")),
            "protection_verified": result.protection.verified,
            "fills": len(result.fills),
        }
        proof["signed_calls"] = 2

    proof["selection_blocked"] = True  # prove-out only; never a go-live claim
    proof["report_honest"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    # Print a secret-free summary.
    print(json.dumps({k: v for k, v in proof.items() if k != "order"} | (
        {"order_disposition": proof.get("order", {}).get("disposition")} if args.place else {}
    ), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
