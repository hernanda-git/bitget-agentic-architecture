"""Read-only Bitget public market adapter.

No credentials, signed endpoints, order methods, or transfer methods exist here.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from src.market.models import Candle, MarketSnapshot


class PublicMarketError(RuntimeError):
    pass


class BitgetPublicClient:
    def __init__(self, base_url: str = "https://api.bitget.com", product_type: str = "USDT-FUTURES",
                 timeout_seconds: float = 5.0, min_interval_seconds: float = 0.05,
                 transport: httpx.AsyncBaseTransport | None = None,
                 clock=time.time) -> None:
        self.base_url = base_url.rstrip("/")
        self.product_type = product_type
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self._last_request = 0.0
        self._transport = transport
        self._clock = clock

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        now = self._clock()
        wait = self.min_interval_seconds - (now - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self._transport) as client:
            response = await client.get(f"{self.base_url}{path}", params=params)
        self._last_request = self._clock()
        if response.status_code == 429:
            raise PublicMarketError("PUBLIC_RATE_LIMIT")
        if response.status_code != 200:
            raise PublicMarketError(f"PUBLIC_HTTP_{response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise PublicMarketError("PUBLIC_INVALID_JSON") from exc
        if not isinstance(payload, dict) or payload.get("code") != "00000":
            raise PublicMarketError("PUBLIC_API_ERROR")
        return payload.get("data")

    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        data = await self._get("/api/v2/mix/market/ticker", {
            "symbol": symbol, "productType": self.product_type,
        })
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise PublicMarketError("TICKER_SCHEMA")
        row = data[0]
        required = ("lastPr", "bidPr", "askPr", "ts")
        if any(key not in row for key in required):
            raise PublicMarketError("TICKER_FIELDS")
        try:
            return {
                "symbol": symbol,
                "mark_price": float(row["lastPr"]),
                "bid": float(row["bidPr"]),
                "ask": float(row["askPr"]),
                "source_ts_ms": int(row["ts"]),
                "funding_rate": None,
                "open_interest": None,
            }
        except (TypeError, ValueError) as exc:
            raise PublicMarketError("TICKER_VALUES") from exc

    async def fetch_candles(self, symbol: str, granularity: str = "1m", limit: int = 100) -> list[Candle]:
        if limit < 1 or limit > 1000:
            raise PublicMarketError("CANDLE_LIMIT")
        data = await self._get("/api/v2/mix/market/candles", {
            "symbol": symbol, "productType": self.product_type,
            "granularity": granularity, "limit": str(limit),
        })
        if not isinstance(data, list):
            raise PublicMarketError("CANDLE_SCHEMA")
        candles = []
        try:
            for row in data:
                if not isinstance(row, list) or len(row) < 6:
                    raise PublicMarketError("CANDLE_FIELDS")
                candles.append(Candle(granularity, float(row[1]), float(row[2]), float(row[3]),
                                      float(row[4]), float(row[5]), int(row[0])))
        except (TypeError, ValueError) as exc:
            if isinstance(exc, PublicMarketError):
                raise
            raise PublicMarketError("CANDLE_VALUES") from exc
        return candles

    async def fetch_snapshot(self, symbol: str, observed_ts_ms: int | None = None) -> MarketSnapshot:
        ticker = await self.fetch_ticker(symbol)
        candles = await self.fetch_candles(symbol)
        observed = observed_ts_ms if observed_ts_ms is not None else int(self._clock() * 1000)
        return MarketSnapshot(**ticker, observed_ts_ms=observed,
                              candles=tuple(candles)).with_hash()
