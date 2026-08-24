"""Local, read-only dashboard server for the demo ledger."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from src.ledger.sqlite import EventLedger

BASE = "https://api.bitget.com"
PRODUCT = "SUSDT-FUTURES"
SYMBOLS = ("SBTCSUSDT", "SETHSUSDT", "SXRPSUSDT")
LEDGER_PATH = ROOT / "data" / "paper.sqlite3"


def load_env():
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def signed_get(path, params):
    load_env()
    assert os.environ.get("BITGET_PRODUCT_TYPE") == PRODUCT
    query = "?" + urlencode(params)
    request_path = path + query
    timestamp = str(int(time.time() * 1000))
    signature = base64.b64encode(hmac.new(os.environ["BITGET_API_SECRET"].encode(), (timestamp + "GET" + request_path).encode(), hashlib.sha256).digest()).decode()
    headers = {"ACCESS-KEY": os.environ["BITGET_API_KEY"], "ACCESS-SIGN": signature, "ACCESS-TIMESTAMP": timestamp, "ACCESS-PASSPHRASE": os.environ["BITGET_PASSPHRASE"], "Content-Type": "application/json", "locale": "en-US"}
    response = httpx.get(BASE + request_path, headers=headers, timeout=10)
    payload = response.json()
    if response.status_code != 200 or payload.get("code") != "00000":
        raise RuntimeError(f"venue_read_{payload.get('code', response.status_code)}")
    return payload.get("data")


def public_get(path, params):
    response = httpx.get(BASE + path, params=params, timeout=10)
    payload = response.json()
    if response.status_code != 200 or payload.get("code") != "00000":
        raise RuntimeError(f"public_read_{payload.get('code', response.status_code)}")
    return payload.get("data")


def _safe(value):
    if isinstance(value, dict):
        return {k: _safe(v) for k, v in value.items() if not any(word in k.lower() for word in ("secret", "key", "token", "pass", "sign"))}
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _status(events, event_names, default="unknown"):
    for event in reversed(events):
        if event["event_type"] in event_names:
            payload = event.get("payload", {})
            value = payload.get("status") or payload.get("state")
            if value:
                return str(value).lower()
    return default


def ledger_state():
    if not LEDGER_PATH.exists():
        events = []
        latest_cycle = None
        positions = []
    else:
        ledger = EventLedger(LEDGER_PATH)
        events = ledger.all()
        latest_cycle = ledger.latest_cycle()
        try:
            positions = ledger.open_positions()
        except (KeyError, ValueError, TypeError):
            positions = []

    provider = _status(events, {"PROVIDER_HEALTHY", "PROVIDER_DEGRADED", "PROVIDER_PARKED"})
    if provider == "unknown":
        provider = next((name for name in ("parked", "degraded", "healthy") if any(e["event_type"] == "PROVIDER_" + name.upper() for e in events)), "unknown")
    market_events = [e for e in events if e["event_type"] == "MARKET_OBSERVED"]
    market_data = "unknown"
    if market_events:
        market_data = "fresh" if int(time.time() * 1000) - market_events[-1]["created_ms"] <= 120_000 else "stale"
    reconciliation = _status(events, {"POSITION_RECONCILED"})
    if reconciliation == "unknown" and events:
        for event in reversed(events):
            if event["event_type"] == "POSITION_RECONCILED":
                reconciliation = "sync" if event.get("payload", {}).get("in_sync") else "drift"
                break
    protection = _status(events, {"PROTECTION_VERIFIED", "PROTECTION_FAILED"}, "idle" if not positions else "unknown")
    if any(e["event_type"] == "PROTECTION_FAILED" for e in events[-20:]):
        protection = "degraded"
    kill_switch = "unknown"
    for event in reversed(events):
        if event["event_type"] in {"KILL_SWITCH", "KILL_SWITCH_STATE"}:
            kill_switch = "engaged" if event.get("payload", {}).get("enabled", False) else "clear"
            break
    counts = {}
    for event in events:
        disposition = event.get("payload", {}).get("disposition")
        if disposition:
            counts[disposition] = counts.get(disposition, 0) + 1
    recent = [{"event_type": e["event_type"], "created_ms": e["created_ms"], "payload": _safe(e.get("payload", {}))} for e in events[-8:]]
    return {"mode": "demo-readonly", "writable": False, "product_type": PRODUCT, "kill_switch": kill_switch, "provider": provider, "market_data": market_data, "reconciliation": reconciliation, "protection": protection, "latest_cycle": _safe(latest_cycle), "disposition_counts": counts, "open_positions": _safe(positions), "recent_events": recent}


def snapshot():
    accounts = signed_get("/api/v2/mix/account/accounts", {"productType": PRODUCT})
    account = next((x for x in accounts if x.get("marginCoin") == "SUSDT"), {}) if isinstance(accounts, list) else {}
    tickers = public_get("/api/v2/mix/market/tickers", {"productType": PRODUCT})
    by_symbol = {x.get("symbol"): x for x in tickers if isinstance(x, dict)}
    markets = [{"symbol": symbol, "mark": by_symbol.get(symbol, {}).get("lastPr"), "bid": by_symbol.get(symbol, {}).get("bidPr"), "ask": by_symbol.get(symbol, {}).get("askPr"), "ts": by_symbol.get(symbol, {}).get("ts")} for symbol in SYMBOLS]
    return {"mode": "demo-readonly", "product_type": PRODUCT, "equity": account.get("usdtEquity") or account.get("equity"), "available": account.get("available"), "margin_coin": account.get("marginCoin"), "open_positions": [], "markets": markets, "updated_ms": int(time.time() * 1000)}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "ui"), **kwargs)

    def do_POST(self): self.send_error(405, "Read-only dashboard")
    def do_PUT(self): self.send_error(405, "Read-only dashboard")
    def do_DELETE(self): self.send_error(405, "Read-only dashboard")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health": return self._json({"ok": True, "mode": "demo-readonly", "product_type": PRODUCT, "writable": False})
        if path == "/api/state": return self._json(ledger_state())
        if path == "/api/snapshot":
            try: return self._json(snapshot())
            except Exception as exc: return self._json({"ok": False, "error": type(exc).__name__}, 503)
        return super().do_GET()

    def _json(self, obj, status=200):
        raw = json.dumps(obj, sort_keys=True).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"): return
        super().log_message(fmt, *args)


def main():
    load_env(); server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler); print("Northline demo-readonly listening on http://127.0.0.1:8765", flush=True); server.serve_forever()


if __name__ == "__main__": main()
