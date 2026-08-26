"""Read-only, unauthenticated Bitget public market adapter.

This module deliberately contains no signing, credentials, order, or account APIs.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from src.market.models import Candle, MarketSnapshot


class PublicMarketError(RuntimeError):
    pass


@dataclass
class RequestMetrics:
    requests: int = 0
    successes: int = 0
    failures: int = 0
    rate_limits: int = 0
    retries: int = 0
    schema_rejections: int = 0
    policy_rejections: int = 0
    latency_ms: list[float] | None = None

    def __post_init__(self):
        if self.latency_ms is None:
            self.latency_ms = []


class BitgetPublicClient:
    CATEGORIES = ("ticker", "candles", "funding", "open_interest")

    def __init__(self, base_url: str = "https://api.bitget.com", product_type: str | None = None,
                 timeout_seconds: float = 5.0, min_interval_seconds: float = 0.05,
                 transport: httpx.AsyncBaseTransport | None = None, clock=time.time,
                 *, venue: str | None = None, max_retries: int = 2, backoff_seconds: float = 0.25,
                 category_intervals: dict[str, float] | None = None, circuit_threshold: int = 3,
                 max_clock_skew_seconds: float = 30.0) -> None:
        self._legacy = venue is None and product_type is None
        if venue is not None and venue.lower() != "bitget":
            raise ValueError("venue must be bitget")
        if venue is None and product_type is not None:
            raise ValueError("venue is required")
        if product_type is not None and product_type not in {"SUSDT-FUTURES"}:
            raise ValueError("incompatible product type")
        self.venue = venue or "bitget"
        self.product_type = product_type or "SUSDT-FUTURES"
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = min(max(float(timeout_seconds), 0.1), 30.0)
        self.min_interval_seconds = max(float(min_interval_seconds), 0.0)
        self._intervals = {c: self.min_interval_seconds for c in self.CATEGORIES}
        self._intervals.update(category_intervals or {})
        self._last_request: dict[str, float] = {c: 0.0 for c in self.CATEGORIES}
        self._transport = transport
        self._clock = clock
        self.max_retries = max(0, min(int(max_retries), 5))
        self.backoff_seconds = min(max(float(backoff_seconds), 0.0), 5.0)
        self.max_clock_skew_seconds = max(float(max_clock_skew_seconds), 0.0)
        self._failures = 0
        self._circuit_threshold = max(1, int(circuit_threshold))
        self.circuit_open = False
        self.metrics = RequestMetrics()

    async def _get(self, path: str, params: dict[str, Any], category: str = "ticker") -> Any:
        if self.circuit_open:
            raise PublicMarketError("PUBLIC_CIRCUIT_OPEN")
        category = category if category in self.CATEGORIES else "ticker"
        wait = self._intervals[category] - (self._clock() - self._last_request[category])
        if wait > 0:
            await asyncio.sleep(wait)
        for attempt in range(self.max_retries + 1):
            started = self._clock()
            self.metrics.requests += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self._transport) as client:
                    response = await client.get(f"{self.base_url}{path}", params=params)
                self._last_request[category] = self._clock()
                elapsed = (self._clock() - started) * 1000
                self.metrics.latency_ms.append(elapsed)
                if response.status_code == 429:
                    self.metrics.rate_limits += 1
                    if attempt < self.max_retries:
                        self.metrics.retries += 1
                        retry_after = min(float(response.headers.get("retry-after", self.backoff_seconds * (2 ** attempt))), 5.0)
                        await asyncio.sleep(max(0.0, retry_after))
                        continue
                    raise PublicMarketError("PUBLIC_RATE_LIMIT")
                if response.status_code >= 500 and attempt < self.max_retries:
                    self.metrics.failures += 1
                    self.metrics.retries += 1
                    await asyncio.sleep(min(self.backoff_seconds * (2 ** attempt), 5.0))
                    continue
                if response.status_code != 200:
                    raise PublicMarketError(f"PUBLIC_HTTP_{response.status_code}")
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise PublicMarketError("PUBLIC_INVALID_JSON") from exc
                if not isinstance(payload, dict) or payload.get("code") != "00000":
                    raise PublicMarketError("PUBLIC_API_ERROR")
                self._failures = 0
                self.metrics.successes += 1
                return payload.get("data")
            except PublicMarketError:
                self.metrics.failures += 1
                self._failures += 1
                if self._failures >= self._circuit_threshold:
                    self.circuit_open = True
                raise
            except (httpx.HTTPError, TimeoutError) as exc:
                self.metrics.failures += 1
                self._failures += 1
                if attempt < self.max_retries:
                    self.metrics.retries += 1
                    await asyncio.sleep(min(self.backoff_seconds * (2 ** attempt), 5.0))
                    continue
                if self._failures >= self._circuit_threshold:
                    self.circuit_open = True
                raise PublicMarketError("PUBLIC_TRANSPORT_ERROR") from exc
        raise PublicMarketError("PUBLIC_RETRY_EXHAUSTED")

    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        data = await self._get("/api/v2/mix/market/ticker", {"symbol": symbol, "productType": self.product_type}, "ticker")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            self.metrics.schema_rejections += 1; raise PublicMarketError("TICKER_SCHEMA")
        row = data[0]
        if any(key not in row for key in ("lastPr", "bidPr", "askPr", "ts")):
            self.metrics.schema_rejections += 1; raise PublicMarketError("TICKER_FIELDS")
        try:
            values = {"symbol": symbol, "mark_price": float(row.get("markPrice", row["lastPr"])), "bid": float(row["bidPr"]),
                      "ask": float(row["askPr"]), "source_ts_ms": int(row["ts"]),
                      "volume": float(row.get("baseVolume", row.get("baseVol", row.get("quoteVol", 0)))),
                      "funding_rate": float(row["fundingRate"]) if row.get("fundingRate") is not None else None,
                      "open_interest": float(row["holdingAmount"]) if row.get("holdingAmount") is not None else None}
        except (TypeError, ValueError) as exc:
            self.metrics.schema_rejections += 1; raise PublicMarketError("TICKER_VALUES") from exc
        if values["bid"] <= 0 or values["ask"] <= 0 or values["bid"] > values["ask"] or values["mark_price"] <= 0:
            self.metrics.policy_rejections += 1; raise PublicMarketError("TICKER_IMPOSSIBLE_PRICES")
        return values

    async def fetch_history_funding_rate(self, symbol: str, limit: int = 100, end_time_ms: int | None = None) -> list[tuple[int, float]]:
        if limit < 1 or limit > 1000: raise PublicMarketError("FUNDING_LIMIT")
        params = {"symbol": symbol, "productType": self.product_type, "pageSize": str(limit)}
        if end_time_ms is not None:
            if end_time_ms <= 0:
                raise PublicMarketError("FUNDING_END_TIME")
            params["endTime"] = str(int(end_time_ms))
        data = await self._get("/api/v2/mix/market/history-fund-rate", params, "funding")
        if not isinstance(data, list):
            self.metrics.schema_rejections += 1; raise PublicMarketError("FUNDING_SCHEMA")
        records = []
        try:
            for row in data:
                if not isinstance(row, dict) or "fundingTime" not in row or "fundingRate" not in row:
                    raise PublicMarketError("FUNDING_FIELDS")
                records.append((int(row["fundingTime"]), float(row["fundingRate"])))
        except (TypeError, ValueError, KeyError) as exc:
            self.metrics.schema_rejections += 1; raise PublicMarketError("FUNDING_VALUES") from exc
        if any(a[0] > b[0] for a, b in zip(records, records[1:])):
            records.sort(key=lambda r: r[0])
        return records

    async def fetch_candles(self, symbol: str, granularity: str = "1m", limit: int = 100,
                            *, end_time_ms: int | None = None, allow_partial: bool = False) -> list[Candle]:
        if limit < 1 or limit > 1000: raise PublicMarketError("CANDLE_LIMIT")
        params = {"symbol": symbol, "productType": self.product_type, "granularity": granularity, "limit": str(limit)}
        if end_time_ms is not None:
            if end_time_ms <= 0:
                raise PublicMarketError("CANDLE_END_TIME")
            params["endTime"] = str(int(end_time_ms))
        data = await self._get("/api/v2/mix/market/candles", params, "candles")
        if not isinstance(data, list) or len(data) < limit and not allow_partial and not self._legacy:
            self.metrics.schema_rejections += 1; raise PublicMarketError("CANDLE_INCOMPLETE_WINDOW")
        candles = []
        try:
            for row in data:
                if not isinstance(row, list) or len(row) < 6: raise PublicMarketError("CANDLE_FIELDS")
                candles.append(Candle(granularity, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), int(row[0])))
        except (TypeError, ValueError) as exc:
            self.metrics.schema_rejections += 1; raise PublicMarketError("CANDLE_VALUES") from exc
        if any(a.source_ts_ms > b.source_ts_ms for a, b in zip(candles, candles[1:])):
            raise PublicMarketError("CANDLE_TIMESTAMP_REGRESSION")
        return candles

    async def fetch_snapshot(self, symbol: str, observed_ts_ms: int | None = None, windows: tuple[str, ...] = ("1m",), limit: int = 100) -> MarketSnapshot:
        ticker = await self.fetch_ticker(symbol)
        candles_by_window = {}
        for window in windows:
            candles_by_window[window] = tuple(await self.fetch_candles(symbol, window, limit))
        observed = observed_ts_ms if observed_ts_ms is not None else int(self._clock() * 1000)
        funding_rate = ticker.get("funding_rate")
        open_interest = ticker.get("open_interest")
        source_timestamps = {"ticker": ticker["source_ts_ms"]}
        if not self._legacy:
            funding_data = await self._get("/api/v2/mix/market/current-fund-rate", {"symbol": symbol, "productType": self.product_type}, "funding")
            oi_data = await self._get("/api/v2/mix/market/open-interest", {"symbol": symbol, "productType": self.product_type}, "open_interest")
            try:
                funding_row = funding_data[0] if isinstance(funding_data, list) else funding_data
                oi_container = oi_data.get("openInterestList", oi_data) if isinstance(oi_data, dict) else oi_data
                oi_row = oi_container[0] if isinstance(oi_container, list) else oi_container
                funding_rate = float(funding_row.get("fundingRate", funding_rate))
                open_interest = float(oi_row.get("openInterest", oi_row.get("holdingAmount", oi_row.get("size"))))
                source_timestamps.update({"funding": int(funding_row.get("fundingTime", ticker["source_ts_ms"])),
                                          "open_interest": int((oi_data.get("ts") if isinstance(oi_data, dict) else None) or ticker["source_ts_ms"])})
            except (TypeError, ValueError, KeyError, IndexError) as exc:
                self.metrics.schema_rejections += 1
                raise PublicMarketError("AUXILIARY_SCHEMA") from exc
        if abs(observed - ticker["source_ts_ms"]) > self.max_clock_skew_seconds * 1000:
            raise PublicMarketError("SOURCE_CLOCK_SKEW")
        return MarketSnapshot(symbol=symbol, mark_price=ticker["mark_price"], bid=ticker["bid"], ask=ticker["ask"],
                              funding_rate=funding_rate, open_interest=open_interest, volume=ticker.get("volume"),
                              observed_ts_ms=observed, source_ts_ms=ticker["source_ts_ms"],
                              candles=candles_by_window[windows[0]], candles_by_window=candles_by_window,
                              required_windows=windows, source_timestamps=source_timestamps).with_hash()
