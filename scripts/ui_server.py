"""Local read-only dashboard server backed only by the local event ledger."""
from __future__ import annotations

import json
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from src.ledger.sqlite import EventLedger
from src.policy.breakers import BreakerRegistry, BreakerStore

PRODUCT = "SUSDT-FUTURES"
LEDGER_PATH = ROOT / "data" / "paper.sqlite3"
# Same breaker store the autonomous runtime writes open fail-closed breakers to
# (provider, market_data, heartbeat, resource, ...). The dashboard only reads it.
BREAKER_PATH = ROOT / "data" / "breakers.json"


def _status(events, names, default="unknown"):
    for event in reversed(events):
        if event["event_type"] in names:
            payload = event.get("payload", {})
            value = payload.get("status") or payload.get("state")
            if value:
                return str(value).lower()
    return default


def _breaker_state():
    """Truthfully project the open fail-closed breakers (e.g. resource pressure).

    Reads the same breaker store the runtime writes. If the store is absent or
    unreadable, reports ``path_present=False`` rather than inventing a state.
    No signed calls, no credentials: this is a pure local-file read.
    """
    try:
        reg = BreakerRegistry(BreakerStore(BREAKER_PATH))
        open_breakers = sorted(reg.snapshot().keys())
        return {
            "open": open_breakers,
            "reason_codes": reg.reason_codes(),
            "path_present": BREAKER_PATH.exists(),
        }
    except Exception:
        return {"open": [], "reason_codes": [], "path_present": False, "error": "unavailable"}


def _approved(value):
    """Project primitive approved facts, never arbitrary ledger payloads."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_approved(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _approved(item) for key, item in value.items()}
    return str(value)


def _cycle_evidence(ledger, cycle):
    cycle_id = cycle.get("cycle_id") if cycle else None
    events = [event for event in ledger.all() if not cycle_id or event.get("cycle_id") == cycle_id]
    evidence = {
        "cycle_id": cycle_id,
        "context_hash": None,
        "decision_status": None,
        "policy_disposition": None,
        "order_ids": [],
        "fill_ids": [],
        "fees": 0.0,
        "funding": 0.0,
        "spread": 0.0,
        "slippage": 0.0,
        "protection_evidence": None,
        "reconciliation_evidence": None,
        "terminal_disposition": cycle.get("terminal_status") if cycle else None,
        "limitations": ["Only facts persisted in the local ledger are shown."]
        if cycle else ["No paper cycle recorded; evidence is unavailable."],
    }
    for event in events:
        payload = event.get("payload", {})
        if event["event_type"] in {"CONTEXT_BUILT", "AGENT_CONTEXT_BUILT"}:
            evidence["context_hash"] = payload.get("context_hash") or payload.get("snapshot_hash")
        if event["event_type"] in {"AGENT_DECISION", "DECISION_REJECTED", "INTENT_APPROVED", "POLICY_REJECTED"}:
            evidence["decision_status"] = payload.get("decision_status") or payload.get("status") or event["event_type"]
            evidence["policy_disposition"] = payload.get("policy_disposition") or payload.get("disposition")
        if event["event_type"] in {"PROTECTION_VERIFIED", "PROTECTION_FAILED", "PROTECTION_TRIGGERED"}:
            evidence["protection_evidence"] = _approved(payload.get("status") or payload.get("state") or event["event_type"])
        if event["event_type"] == "POSITION_RECONCILED":
            evidence["reconciliation_evidence"] = _approved(payload.get("status") or ("SYNC" if payload.get("in_sync") else "DRIFT"))
        for field in ("fee", "funding", "spread", "slippage"):
            try:
                evidence[field + "s" if field == "fee" else field] += float(payload.get(field, 0) or 0)
            except (TypeError, ValueError):
                evidence["limitations"].append(f"Non-numeric {field} was omitted.")
        for field, target in (("venue_order_id", "order_ids"), ("order_id", "order_ids"), ("client_order_id", "order_ids"), ("fill_id", "fill_ids")):
            if payload.get(field) is not None and str(payload[field]) not in evidence[target]:
                evidence[target].append(str(payload[field]))
    for row in ledger.table_rows("orders") + ledger.table_rows("fills"):
        if not cycle_id or row.get("cycle_id") == cycle_id:
            payload = json.loads(row.get("event_json", "{}"))
            if row.get("venue_order_id") or row.get("client_order_id"):
                for item in (row.get("venue_order_id"), row.get("client_order_id")):
                    if item and str(item) not in evidence["order_ids"]:
                        evidence["order_ids"].append(str(item))
            if row.get("fill_id") and str(row["fill_id"]) not in evidence["fill_ids"]:
                evidence["fill_ids"].append(str(row["fill_id"]))
            for field in ("fee", "funding", "spread", "slippage"):
                try:
                    evidence[field + "s" if field == "fee" else field] += float(payload.get(field, 0) or 0)
                except (TypeError, ValueError):
                    pass
    return evidence


def ledger_state():
    ledger = EventLedger(LEDGER_PATH)
    events = ledger.all()
    latest_cycle = ledger.latest_cycle()
    try:
        positions = ledger.open_positions()
    except (KeyError, ValueError, TypeError):
        positions = []
    provider = _status(events, {"PROVIDER_HEALTHY", "PROVIDER_DEGRADED", "PROVIDER_PARKED"})
    if provider == "unknown":
        provider = next((name for name in ("parked", "degraded", "healthy") if any(event["event_type"] == "PROVIDER_" + name.upper() for event in events)), "unknown")
    market_events = [event for event in events if event["event_type"] == "MARKET_OBSERVED"]
    market_data = "unknown"
    if market_events:
        market_data = "fresh" if int(time.time() * 1000) - market_events[-1]["created_ms"] <= 120_000 else "stale"
    reconciliation = _status(events, {"POSITION_RECONCILED"})
    if reconciliation == "unknown":
        for event in reversed(events):
            if event["event_type"] == "POSITION_RECONCILED":
                reconciliation = "sync" if event.get("payload", {}).get("in_sync") else "drift"
                break
    protection = _status(events, {"PROTECTION_VERIFIED", "PROTECTION_FAILED"})
    if any(event["event_type"] == "PROTECTION_FAILED" for event in events[-20:]):
        protection = "degraded"
    kill_switch = "unknown"
    for event in reversed(events):
        if event["event_type"] in {"KILL_SWITCH", "KILL_SWITCH_STATE"}:
            kill_switch = "engaged" if event.get("payload", {}).get("enabled", False) else "clear"
            break
    counts = ledger.disposition_counts()
    recent = [{"event_type": event["event_type"], "created_ms": event["created_ms"], "source": "ledger"} for event in events[-8:]]
    return {"mode": "demo-readonly", "writable": False, "product_type": PRODUCT, "sources": ["ledger"], "kill_switch": kill_switch, "provider": provider, "market_data": market_data, "reconciliation": reconciliation, "protection": protection, "breakers": _breaker_state(), "latest_cycle": _approved(latest_cycle), "latest_evidence": _cycle_evidence(ledger, latest_cycle), "disposition_counts": counts, "open_positions": _approved(positions), "recent_events": recent}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "ui"), **kwargs)

    def do_POST(self):
        self.send_error(405, "Read-only dashboard")

    def do_PUT(self):
        self.send_error(405, "Read-only dashboard")

    def do_DELETE(self):
        self.send_error(405, "Read-only dashboard")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            return self._json({"ok": True, "mode": "demo-readonly", "product_type": PRODUCT, "writable": False})
        if path == "/api/state":
            return self._json(ledger_state())
        return super().do_GET()

    def _json(self, obj, status=200):
        raw = json.dumps(obj, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            return
        super().log_message(fmt, *args)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Northline demo-readonly listening on http://127.0.0.1:8765", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
