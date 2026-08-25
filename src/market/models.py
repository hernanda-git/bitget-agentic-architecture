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
        if not self.timeframe or min(self.open, self.high, self.low, self.close, self.volume) < 0:
            raise ValueError("candle values cannot be negative")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("candle prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close) or self.high < self.low:
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
    volume: float | None = None
    candles_by_window: dict[str, tuple[Candle, ...]] = field(default_factory=dict)
    source_timestamps: dict[str, int] = field(default_factory=dict)
    feature_version: str = "market-v1"
    required_windows: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.symbol.isupper() or not self.symbol.endswith("USDT"):
            raise ValueError("invalid symbol")
        if min(self.mark_price, self.bid, self.ask) <= 0:
            raise ValueError("prices must be positive")
        if self.bid > self.ask:
            raise ValueError("impossible price relationship")
        if self.observed_ts_ms <= 0 or self.source_ts_ms <= 0:
            raise ValueError("timestamps must be positive")
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError("open interest cannot be negative")
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume cannot be negative")
        if self.required_windows and any(window not in self.candles_by_window for window in self.required_windows):
            raise ValueError("incomplete candle windows")
        for window in self.required_windows:
            if not self.candles_by_window[window]:
                raise ValueError("incomplete candle windows")
        if any(c.source_ts_ms > self.observed_ts_ms + 30_000 for c in self.candles):
            raise ValueError("candle source timestamp is in the future")

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def freshness_ms(self) -> int:
        return max(0, self.observed_ts_ms - self.source_ts_ms)

    def canonical(self) -> dict:
        windows = {k: [c.__dict__ for c in v] for k, v in sorted(self.candles_by_window.items())}
        return {"symbol": self.symbol, "mark_price": self.mark_price, "bid": self.bid, "ask": self.ask,
                "spread": self.spread, "funding_rate": self.funding_rate, "open_interest": self.open_interest,
                "volume": self.volume, "observed_ts_ms": self.observed_ts_ms, "source_ts_ms": self.source_ts_ms,
                "source_timestamps": dict(sorted(self.source_timestamps.items())), "feature_version": self.feature_version,
                "candles": [c.__dict__ for c in self.candles], "candles_by_window": windows,
                "required_windows": list(self.required_windows)}

    def computed_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.canonical(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def with_hash(self) -> "MarketSnapshot":
        return replace(self, snapshot_hash=self.computed_hash())

    @property
    def spread_bps(self) -> float:
        return (self.spread / self.mark_price) * 10_000
