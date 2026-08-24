"""Small in-memory snapshot store. Persistence belongs to the ledger phase."""
from __future__ import annotations

from src.market.models import MarketSnapshot


class SnapshotStore:
    def __init__(self) -> None:
        self._latest: dict[str, MarketSnapshot] = {}

    def put(self, snapshot: MarketSnapshot) -> None:
        previous = self._latest.get(snapshot.symbol)
        if previous is not None and snapshot.observed_ts_ms < previous.observed_ts_ms:
            raise ValueError("market timestamp regression")
        self._latest[snapshot.symbol] = snapshot

    def get(self, symbol: str) -> MarketSnapshot | None:
        return self._latest.get(symbol)
