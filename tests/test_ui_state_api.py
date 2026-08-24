import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from scripts import ui_server
from src.ledger.sqlite import EventLedger


def _serve(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_server, "LEDGER_PATH", tmp_path / "ledger.sqlite3")
    server = ui_server.ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _get(server, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}{path}") as response:
        return response.status, json.loads(response.read()), response.headers


def test_state_empty_ledger_is_exact_read_only_projection(monkeypatch, tmp_path):
    server = _serve(monkeypatch, tmp_path)
    try:
        status, body, _ = _get(server, "/api/state")
    finally:
        server.shutdown()
    assert status == 200
    assert body == {
        "mode": "demo-readonly",
        "writable": False,
        "product_type": "SUSDT-FUTURES",
        "kill_switch": "unknown",
        "provider": "unknown",
        "market_data": "unknown",
        "reconciliation": "unknown",
        "protection": "idle",
        "latest_cycle": None,
        "disposition_counts": {},
        "open_positions": [],
        "recent_events": [],
    }


def test_state_projects_ledger_summaries_without_credentials(monkeypatch, tmp_path):
    ledger_path = tmp_path / "ledger.sqlite3"
    ledger = EventLedger(ledger_path)
    assert ledger.claim_cycle("cycle-1")
    ledger.append("AGENT_DECISION", {"cycle_id": "cycle-1", "disposition": "APPROVED"})
    ledger.append("PROVIDER_DEGRADED", {"cycle_id": "cycle-1"})
    ledger.append("POSITION_RECONCILED", {"cycle_id": "cycle-1", "in_sync": True})
    ledger.append("PROTECTION_VERIFIED", {"cycle_id": "cycle-1", "status": "PROTECTED"})
    ledger.set_terminal("cycle-1", "COMPLETED")
    monkeypatch.setattr(ui_server, "LEDGER_PATH", ledger_path)
    body = ui_server.ledger_state()
    assert body["latest_cycle"]["cycle_id"] == "cycle-1"
    assert body["disposition_counts"] == {"APPROVED": 1}
    assert body["provider"] == "degraded"
    assert body["market_data"] == "unknown"
    assert body["reconciliation"] == "sync"
    assert body["protection"] == "protected"
    assert body["open_positions"] == []
    assert "BITGET_API_SECRET" not in json.dumps(body)
    assert "ACCESS-KEY" not in json.dumps(body)


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_state_api_rejects_mutation_methods(monkeypatch, tmp_path, method):
    server = _serve(monkeypatch, tmp_path)
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/api/state", method=method
    )
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request)
    finally:
        server.shutdown()
    assert exc.value.code == 405


def test_health_is_explicitly_read_only(monkeypatch, tmp_path):
    server = _serve(monkeypatch, tmp_path)
    try:
        status, body, _ = _get(server, "/api/health")
    finally:
        server.shutdown()
    assert status == 200
    assert body == {"mode": "demo-readonly", "product_type": "SUSDT-FUTURES", "writable": False, "ok": True}
