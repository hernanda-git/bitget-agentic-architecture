import json

import httpx
import pytest

from src.execution.bitget_demo import (
    DEMO_PRODUCT_TYPE,
    BitgetDemoAdapter,
    DemoExecutionBlocked,
    DemoExecutionConfigError,
    ProtectionVerification,
)


class Recorder:
    def __init__(self, payloads):
        self.requests = []
        self.payloads = payloads

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/place-order"):
            return httpx.Response(200, json={"code": "00000", "data": {"orderId": "oid-1", "clientOid": "cid"}})
        if path.endswith("/detail"):
            return httpx.Response(200, json={"code": "00000", "data": {"orderId": "oid-1", "clientOid": "cid", "status": "filled", "presetStopLossPrice": "90", "presetStopSurplusPrice": "110"}})
        if path.endswith("/fills"):
            return httpx.Response(200, json={"code": "00000", "data": [{"orderId": "oid-1", "fillPrice": "100", "fillSize": "1"}]})
        if path.endswith("/all-position"):
            return httpx.Response(200, json={"code": "00000", "data": [{"symbol": "BTCUSDT", "total": "1", "holdSide": "buy", "stopLoss": "90", "takeProfit": "110"}]})
        return httpx.Response(404, json={"code": "404"})


def adapter(recorder, monkeypatch, **kwargs):
    monkeypatch.setenv("DEMO_EXECUTION_CONFIRM", "1")
    return BitgetDemoAdapter(
        base_url="https://demo-api.bitget.com",
        api_key="key",
        api_secret="secret",
        passphrase="phrase",
        transport=httpx.MockTransport(recorder),
        **kwargs,
    )


def test_gate_blocks_before_transport_without_confirmation(monkeypatch):
    called = []
    transport = httpx.MockTransport(lambda request: called.append(request) or httpx.Response(200, json={}))
    client = BitgetDemoAdapter(base_url="http://127.0.0.1:9", transport=transport)

    with pytest.raises(DemoExecutionBlocked, match="DEMO_EXECUTION_CONFIRM=1"):
        client.submit_order({"symbol": "BTCUSDT", "side": "buy"})
    assert called == []


def test_constructor_rejects_unsafe_configuration(monkeypatch):
    monkeypatch.setenv("DEMO_EXECUTION_CONFIRM", "1")
    with pytest.raises(DemoExecutionConfigError):
        BitgetDemoAdapter(base_url="https://api.bitget.com")
    with pytest.raises(DemoExecutionConfigError):
        BitgetDemoAdapter(base_url="https://demo-api.bitget.com", product_type="USDT-FUTURES")
    with pytest.raises(DemoExecutionConfigError):
        BitgetDemoAdapter(base_url="https://demo-api.bitget.com", mode="live")
    with pytest.raises(DemoExecutionConfigError):
        BitgetDemoAdapter(base_url="https://demo-api.bitget.com", dry_run=False)


def test_client_id_is_deterministic_and_order_is_explicitly_demo(monkeypatch):
    recorder = Recorder({})
    client = adapter(recorder, monkeypatch)
    order = {"symbol": "BTCUSDT", "side": "buy", "size": "1", "stop_loss": "90", "take_profit": "110"}
    first = client.client_order_id(order)
    second = client.client_order_id(dict(reversed(order.items())))
    assert first == second
    result = client.submit_order(order)
    assert result["orderId"] == "oid-1"
    request = recorder.requests[0]
    body = json.loads(request.content)
    assert body["productType"] == DEMO_PRODUCT_TYPE
    assert body["clientOid"] == first
    assert request.headers["paptrading"] == "1"


def test_execute_flow_reads_order_fills_positions_and_parks_without_protection(monkeypatch):
    class Unprotected(Recorder):
        def __call__(self, request):
            response = super().__call__(request)
            if request.url.path.endswith("/detail"):
                return httpx.Response(200, json={"code": "00000", "data": {"orderId": "oid-1", "status": "filled"}})
            if request.url.path.endswith("/all-position"):
                return httpx.Response(200, json={"code": "00000", "data": [{"symbol": "BTCUSDT", "total": "1"}]})
            return response

    recorder = Unprotected({})
    client = adapter(recorder, monkeypatch)
    result = client.execute({"symbol": "BTCUSDT", "side": "buy", "size": "1"})
    assert result.disposition == "PARKED_PROTECTION_MISSING"
    assert result.protection.verified is False
    assert [request.url.path for request in recorder.requests] == [
        "/api/v2/mix/order/place-order",
        "/api/v2/mix/order/detail",
        "/api/v2/mix/order/fills",
        "/api/v2/mix/position/all-position",
    ]


def test_typed_reads_and_protection_result(monkeypatch):
    recorder = Recorder({})
    client = adapter(recorder, monkeypatch)
    assert client.read_order("oid-1")["status"] == "filled"
    assert client.read_fills("BTCUSDT")[0]["fillSize"] == "1"
    assert client.read_positions("BTCUSDT")[0]["symbol"] == "BTCUSDT"
    assert client.verify_protection({"stopLoss": "90", "takeProfit": "110"}) == ProtectionVerification(True, "PROTECTION_PRESENT")
    assert client.verify_protection({}) == ProtectionVerification(False, "PROTECTION_MISSING")


def test_unsupported_operations_and_arbitrary_paths_are_not_exposed(monkeypatch):
    client = adapter(Recorder({}), monkeypatch)
    assert not hasattr(client, "transfer")
    assert not hasattr(client, "withdraw")
    assert not hasattr(client, "set_leverage")
    with pytest.raises(DemoExecutionConfigError):
        client._request("GET", "/api/v2/mix/account/transfer")
