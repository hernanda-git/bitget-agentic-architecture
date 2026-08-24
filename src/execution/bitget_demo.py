"""Explicitly gated, fail-closed Bitget demo execution adapter.

This module is intentionally small. It signs only a fixed allow-list of Bitget
classic futures demo endpoints and never loads credentials from disk.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode

import httpx

DEMO_PRODUCT_TYPE = "SUSDT-FUTURES"
_ALLOWED_HOSTS = {"demo-api.bitget.com", "api-demo.bitget.com"}
_ALLOWED_PATHS = {
    "POST /api/v2/mix/order/place-order",
    "GET /api/v2/mix/order/detail",
    "GET /api/v2/mix/order/fills",
    "GET /api/v2/mix/position/all-position",
}


class DemoExecutionBlocked(RuntimeError):
    """Raised before any transport call when the explicit execution gate is absent."""


class DemoExecutionConfigError(ValueError):
    """Raised for a configuration that could target production or mutate unsafe state."""


class DemoAPIError(RuntimeError):
    """Raised for transport, HTTP, or Bitget API failures."""


@dataclass(frozen=True)
class ProtectionVerification:
    verified: bool
    reason: str


@dataclass(frozen=True)
class DemoExecutionResult:
    disposition: str
    order: Mapping[str, Any]
    fills: tuple[Mapping[str, Any], ...]
    positions: tuple[Mapping[str, Any], ...]
    protection: ProtectionVerification


class BitgetDemoAdapter:
    """Typed Bitget demo adapter with a hard safety boundary.

    Credentials are constructor inputs only. The default transport is httpx and
    can be replaced with ``httpx.MockTransport`` in tests.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        product_type: str = DEMO_PRODUCT_TYPE,
        mode: str = "demo",
        dry_run: bool = True,
        withdrawals_enabled: bool = False,
        transfers_enabled: bool = False,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        clock=time.time,
    ) -> None:
        parsed = httpx.URL(base_url)
        if parsed.scheme != "https" and parsed.host not in {"127.0.0.1", "localhost"}:
            raise DemoExecutionConfigError("demo base URL must use HTTPS")
        if parsed.host in {"api.bitget.com", "www.bitget.com", "vip-api.bitget.com", "capi.bitget.com"}:
            raise DemoExecutionConfigError("production base URL is forbidden")
        if parsed.host not in _ALLOWED_HOSTS and parsed.host not in {"127.0.0.1", "localhost"}:
            raise DemoExecutionConfigError("base URL is not an allow-listed demo endpoint")
        if product_type != DEMO_PRODUCT_TYPE:
            raise DemoExecutionConfigError("only SUSDT-FUTURES demo product is allowed")
        if mode == "live":
            raise DemoExecutionConfigError("live mode is forbidden")
        if mode not in {"demo", "testnet"}:
            raise DemoExecutionConfigError("mode must be demo or testnet")
        if not dry_run:
            raise DemoExecutionConfigError("dry_run=false is forbidden")
        if withdrawals_enabled or transfers_enabled:
            raise DemoExecutionConfigError("transfers and withdrawals are forbidden")
        self.base_url = str(base_url).rstrip("/")
        self.api_key, self.api_secret, self.passphrase = api_key, api_secret, passphrase
        self.timeout_seconds, self._transport, self._clock = timeout_seconds, transport, clock

    def client_order_id(self, order: Mapping[str, Any]) -> str:
        canonical = json.dumps(dict(order), sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:24]
        return f"agentic-demo-{digest}"

    def _gate(self) -> None:
        if os.environ.get("DEMO_EXECUTION_CONFIRM") != "1":
            raise DemoExecutionBlocked("DEMO_EXECUTION_CONFIRM=1 required")

    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None, body: Mapping[str, Any] | None = None) -> Any:
        self._gate()
        key = f"{method.upper()} {path}"
        if key not in _ALLOWED_PATHS:
            raise DemoExecutionConfigError("endpoint is not allowed by demo adapter")
        query = urlencode([(k, str(v)) for k, v in (params or {}).items()])
        request_path = path + (("?" + query) if query else "")
        content = json.dumps(body, sort_keys=True, separators=(",", ":")) if body is not None else ""
        timestamp = str(int(self._clock() * 1000))
        prehash = timestamp + method.upper() + request_path + content
        signature = base64.b64encode(hmac.new(self.api_secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()
        headers = {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "paptrading": "1",
        }
        with httpx.Client(timeout=self.timeout_seconds, transport=self._transport) as client:
            response = client.request(method, self.base_url + request_path, content=content or None, headers=headers)
        try:
            payload = response.json()
        except ValueError as exc:
            raise DemoAPIError("DEMO_INVALID_JSON") from exc
        if response.status_code != 200 or not isinstance(payload, dict) or payload.get("code") != "00000":
            raise DemoAPIError(f"DEMO_API_ERROR http={response.status_code} code={payload.get('code') if isinstance(payload, dict) else 'invalid'}")
        return payload.get("data")

    def submit_order(self, order: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = dict(order)
        payload["productType"] = DEMO_PRODUCT_TYPE
        payload["clientOid"] = self.client_order_id(order)
        return self._request("POST", "/api/v2/mix/order/place-order", body=payload)

    def read_order(self, order_id: str, *, client_oid: str | None = None) -> Mapping[str, Any]:
        params = {"productType": DEMO_PRODUCT_TYPE}
        if order_id:
            params["orderId"] = order_id
        if client_oid:
            params["clientOid"] = client_oid
        data = self._request("GET", "/api/v2/mix/order/detail", params=params)
        return data if isinstance(data, dict) else {}

    def read_fills(self, symbol: str, *, order_id: str | None = None) -> tuple[Mapping[str, Any], ...]:
        params: dict[str, Any] = {"productType": DEMO_PRODUCT_TYPE, "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        data = self._request("GET", "/api/v2/mix/order/fills", params=params)
        rows = data.get("fillList", []) if isinstance(data, dict) else data
        return tuple(row for row in (rows or []) if isinstance(row, dict))

    def read_positions(self, symbol: str | None = None) -> tuple[Mapping[str, Any], ...]:
        params: dict[str, Any] = {"productType": DEMO_PRODUCT_TYPE}
        if symbol:
            params["symbol"] = symbol
        data = self._request("GET", "/api/v2/mix/position/all-position", params=params)
        rows = data.get("list", []) if isinstance(data, dict) else data
        return tuple(row for row in (rows or []) if isinstance(row, dict))

    def reconcile(self, symbol: str, order_id: str) -> dict[str, Any]:
        order = self.read_order(order_id)
        fills = self.read_fills(symbol, order_id=order_id)
        positions = self.read_positions(symbol)
        return {"order": order, "fills": fills, "positions": positions}

    def verify_protection(self, observation: Mapping[str, Any]) -> ProtectionVerification:
        stop = observation.get("stopLoss", observation.get("presetStopLossPrice"))
        take = observation.get("takeProfit", observation.get("presetStopSurplusPrice"))
        if stop not in (None, "", "0", 0) and take not in (None, "", "0", 0):
            return ProtectionVerification(True, "PROTECTION_PRESENT")
        return ProtectionVerification(False, "PROTECTION_MISSING")

    def execute(self, order: Mapping[str, Any]) -> DemoExecutionResult:
        submitted = self.submit_order(order)
        order_id = str(submitted.get("orderId", ""))
        if not order_id:
            raise DemoAPIError("DEMO_ORDER_ID_MISSING")
        symbol = str(order["symbol"])
        evidence = self.reconcile(symbol, order_id)
        protection = self.verify_protection(evidence["order"])
        disposition = "EXECUTED_PROTECTED" if protection.verified else "PARKED_PROTECTION_MISSING"
        return DemoExecutionResult(disposition, evidence["order"], evidence["fills"], evidence["positions"], protection)
