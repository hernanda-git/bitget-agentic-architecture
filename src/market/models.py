"""Normalized, immutable market snapshot models."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Candle:
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source_ts_ms: int

    def __post_init__(self) -> None:
        if min(self.open, self.high, self.low, self.close, self.volume) < 0:
            raise ValueError("candle values cannot be negative")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("invalid candle geometry")
        if self.source_ts_ms <= 0:
            raise ValueError("candle timestamp must be positive")


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    mark_price: float
    bid: float
    ask: float
    funding_rate: float | None
    open_interest: float | None
    observed_ts_ms: int
    source_ts_ms: int
    candles: tuple[Candle, ...] = field(default_factory=tuple)
    snapshot_hash: str = ""

    def __post_init__(self) -> None:
        if not self.symbol.isupper() or not self.symbol.endswith("USDT"):
            raise ValueError("invalid symbol")
        if self.mark_price <= 0 or self.bid <= 0 or self.ask <= 0:
            raise ValueError("prices must be positive")
        if self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")
        if self.observed_ts_ms <= 0 or self.source_ts_ms <= 0:
            raise ValueError("timestamps must be positive")
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError("open interest cannot be negative")

    def canonical(self) -> dict:
        return {
            "symbol": self.symbol,
            "mark_price": self.mark_price,
            "bid": self.bid,
            "ask": self.ask,
            "funding_rate": self.funding_rate,
            "open_interest": self.open_interest,
            "observed_ts_ms": self.observed_ts_ms,
            "source_ts_ms": self.source_ts_ms,
            "candles": [c.__dict__ for c in self.candles],
        }

    def computed_hash(self) -> str:
        payload = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()

    def with_hash(self) -> "MarketSnapshot":
        return replace(self, snapshot_hash=self.computed_hash())

    @property
    def spread_bps(self) -> float:
        return ((self.ask - self.bid) / self.mark_price) * 10_000
