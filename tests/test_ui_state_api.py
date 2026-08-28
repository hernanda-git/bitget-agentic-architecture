import json
import inspect
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from scripts import ui_server
from src.ledger.sqlite import EventLedger


def _serve(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_server, "LEDGER_PATH", tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(ui_server, "BREAKER_PATH", tmp_path / "breakers.json")
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
        "sources": ["ledger"],
        "kill_switch": "unknown",
        "provider": "unknown",
        "market_data": "unknown",
        "reconciliation": "unknown",
        "protection": "unknown",
        "breakers": {"open": [], "reason_codes": [], "path_present": False},
        "latest_cycle": None,
        "latest_evidence": {
            "context_hash": None,
            "cycle_id": None,
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
            "terminal_disposition": None,
            "limitations": ["No paper cycle recorded; evidence is unavailable."],
        },
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


def test_state_projection_contains_approved_latest_cycle_evidence_only(monkeypatch, tmp_path):
    ledger_path = tmp_path / "ledger.sqlite3"
    ledger = EventLedger(ledger_path)
    ledger.claim_cycle("cycle-evidence", trace_id="trace-1", mode="paper", symbol="BTCUSDT")
    ledger.append_event({"event_type": "CONTEXT_BUILT", "cycle_id": "cycle-evidence", "trace_id": "trace-1", "mode": "paper", "product_type": "SUSDT-FUTURES", "symbol": "BTCUSDT", "created_ms": 1000, "payload": {"context_hash": "ctx-hash", "secret": "must-not-render"}})
    ledger.append_event({"event_type": "AGENT_DECISION", "cycle_id": "cycle-evidence", "trace_id": "trace-1", "mode": "paper", "product_type": "SUSDT-FUTURES", "symbol": "BTCUSDT", "created_ms": 1001, "payload": {"decision_status": "APPROVED", "policy_disposition": "ALLOW", "api_key": "must-not-render"}})
    ledger.set_terminal("cycle-evidence", "COMPLETED")
    monkeypatch.setattr(ui_server, "LEDGER_PATH", ledger_path)

    body = ui_server.ledger_state()
    evidence = body["latest_evidence"]
    assert evidence["cycle_id"] == "cycle-evidence"
    assert evidence["context_hash"] == "ctx-hash"
    assert evidence["decision_status"] == "APPROVED"
    assert evidence["policy_disposition"] == "ALLOW"
    assert evidence["terminal_disposition"] == "COMPLETED"
    assert "secret" not in json.dumps(body).lower()
    assert "api_key" not in json.dumps(body).lower()


def test_ui_server_has_no_credential_or_signed_read_surface():
    source = inspect.getsource(ui_server)
    for forbidden in ("signed_get", "BITGET_API_SECRET", "ACCESS-KEY", "hmac", "httpx"):
        assert forbidden not in source


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


def test_state_includes_breaker_status_surface(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_server, "LEDGER_PATH", tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(ui_server, "BREAKER_PATH", tmp_path / "breakers.json")
    body = ui_server.ledger_state()
    assert "breakers" in body
    assert body["breakers"]["open"] == []
    assert body["breakers"]["path_present"] is False
    assert "BITGET_API_SECRET" not in json.dumps(body)


def test_state_projects_open_resource_breaker_when_present(monkeypatch, tmp_path):
    from src.policy.breakers import BreakerRegistry, BreakerStore

    monkeypatch.setattr(ui_server, "LEDGER_PATH", tmp_path / "ledger.sqlite3")
    breaker_path = tmp_path / "breakers.json"
    monkeypatch.setattr(ui_server, "BREAKER_PATH", breaker_path)
    reg = BreakerRegistry(BreakerStore(breaker_path))
    reg.trip("resource", "resource pressure: LOW_AVAILABLE_MEMORY")
    body = ui_server.ledger_state()
    assert body["breakers"]["open"] == ["resource"]
    assert "RESOURCE_BREAKER" in body["breakers"]["reason_codes"]
    assert body["breakers"]["path_present"] is True
    # Still no credentials or signed-call surface, only a local breaker read.
    assert "BITGET_API_SECRET" not in json.dumps(body)
