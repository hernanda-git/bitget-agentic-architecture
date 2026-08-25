"""Deterministic market events for offline replay."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class MarketEvent:
    symbol: str
    bid: float
    ask: float
    mark: float
    sequence: int
    timestamp_ms: int = 0
    funding_rate: float = 0.0
