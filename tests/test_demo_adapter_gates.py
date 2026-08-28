"""P1: prove the Bitget demo adapter safety boundary holds by construction.

The adapter is intentionally isolated (NOT imported by src/runtime/canonical).
We prove its hard gates with httpx.MockTransport so NO real signed call or
network egress occurs. This is the honest offline "prove-out": the boundary
rejects production hosts, live mode, withdrawals, and non-allow-listed
endpoints, and requires the explicit DEMO_EXECUTION_CONFIRM=1 gate.
"""
from __future__ import annotations

import httpx
import os

from src.execution.bitget_demo import (
    BitgetDemoAdapter,
    DemoExecutionBlocked,
    DemoExecutionConfigError,
)


def _mock_transport():
    def handler(request):
        return httpx.Response(200, json={"code": "00000", "data": {"orderId": "1"}})
    return httpx.MockTransport(handler)


def test_production_host_rejected():
    for host in ("api.bitget.com", "www.bitget.com", "vip-api.bitget.com", "capi.bitget.com"):
        try:
            BitgetDemoAdapter(base_url=f"https://{host}", api_key="k", api_secret="s", passphrase="p")
            assert False, f"production host {host} must be rejected"
        except DemoExecutionConfigError:
            pass


def test_non_demo_host_rejected():
    try:
        BitgetDemoAdapter(base_url="https://evil.example.com", api_key="k", api_secret="s", passphrase="p")
        assert False, "non-allowlisted host must be rejected"
    except DemoExecutionConfigError:
        pass


def test_live_mode_and_withdrawals_rejected():
    try:
        BitgetDemoAdapter(base_url="https://demo-api.bitget.com", mode="live")
        assert False, "live mode must be rejected"
    except DemoExecutionConfigError:
        pass
    try:
        BitgetDemoAdapter(base_url="https://demo-api.bitget.com", withdrawals_enabled=True)
        assert False, "withdrawals must be rejected"
    except DemoExecutionConfigError:
        pass
    try:
        BitgetDemoAdapter(base_url="https://demo-api.bitget.com", dry_run=False)
        assert False, "dry_run=False must be rejected"
    except DemoExecutionConfigError:
        pass


def test_confirm_gate_required(monkeypatch):
    monkeypatch.delenv("DEMO_EXECUTION_CONFIRM", raising=False)
    adapter = BitgetDemoAdapter(base_url="https://demo-api.bitget.com", transport=_mock_transport())
    try:
        adapter.submit_order({"symbol": "BTCUSDT", "side": "BUY", "size": "1", "price": "100"})
        assert False, "DEMO_EXECUTION_CONFIRM=1 must be required"
    except DemoExecutionBlocked:
        pass


def test_allowed_endpoint_signed_call_succeeds_with_confirm(monkeypatch):
    monkeypatch.setenv("DEMO_EXECUTION_CONFIRM", "1")
    captured = {}

    def handler(request):
        captured["host"] = str(request.url.host)
        captured["path"] = str(request.url.path)
        captured["method"] = request.method
        return httpx.Response(200, json={"code": "00000", "data": {"orderId": "abc"}})

    adapter = BitgetDemoAdapter(
        base_url="https://demo-api.bitget.com",
        api_key="k", api_secret="s", passphrase="p",
        transport=httpx.MockTransport(handler),
    )
    order = {"symbol": "BTCUSDT", "side": "BUY", "size": "1", "price": "100"}
    result = adapter.submit_order(order)
    # The signed call only ever targets the allow-listed demo host + path.
    assert captured["host"] == "demo-api.bitget.com"
    assert captured["path"] == "/api/v2/mix/order/place-order"
    assert result["orderId"] == "abc"
