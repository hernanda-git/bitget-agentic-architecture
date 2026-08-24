from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Any

from .models import InMemoryProtectionStore, ProtectionRecord, ProtectionState


@dataclass(frozen=True)
class ProtectionEvent:
    kind: str
    symbol: str
    reason: str = ""


class MarkMonitor:
    def __init__(self, store: Any | None = None, close_position: Callable[[str], Any] | None = None, *, stale_after: float = 5.0, clock: Callable[[], float] | None = None) -> None:
        self.store = store or InMemoryProtectionStore()
        self.close_position = close_position or (lambda symbol: None)
        self.stale_after = stale_after
        self.clock = clock or time.time
        self._records = {symbol: ProtectionRecord.from_dict(data) for symbol, data in self.store.load_all().items()}
        self._last_marks: dict[str, float] = {}

    @property
    def entries_parked(self) -> bool:
        return any(record.state in {ProtectionState.DEGRADED, ProtectionState.UNKNOWN, ProtectionState.EMERGENCY_EXIT_PENDING} for record in self._records.values())

    def _save(self, record: ProtectionRecord) -> None:
        self._records[record.symbol] = record
        self.store.save(record)

    def arm(self, symbol: str, side: str, quantity: float, stop_loss: float, take_profit: float, *, timestamp: float | None = None) -> ProtectionRecord:
        record = ProtectionRecord(symbol, side.upper(), quantity, stop_loss, take_profit, ProtectionState.PROTECTED, timestamp or self.clock())
        self._save(record)
        return record

    def get(self, symbol: str) -> ProtectionRecord:
        return self._records[symbol]

    def state(self, symbol: str) -> ProtectionState:
        return self.get(symbol).state

    def _fresh(self, timestamp: float) -> bool:
        return self.clock() - timestamp <= self.stale_after

    def on_mark(self, symbol: str, price: float, *, timestamp: float | None = None) -> list[ProtectionEvent]:
        record = self.get(symbol)
        timestamp = self.clock() if timestamp is None else timestamp
        self._last_marks[symbol] = timestamp
        if not self._fresh(timestamp):
            return self._degrade(symbol, "STALE_MARK")
        if record.state is ProtectionState.CLOSED:
            return []
        breached = False
        if record.stop_loss is not None and record.take_profit is not None:
            breached = ((record.side == "LONG" and (price <= record.stop_loss or price >= record.take_profit)) or
                        (record.side == "SHORT" and (price >= record.stop_loss or price <= record.take_profit)))
        if not breached or record.state is ProtectionState.EMERGENCY_EXIT_PENDING:
            return []
        self._save(ProtectionRecord(**{**record.to_dict(), "state": ProtectionState.CLOSED, "updated_at": timestamp}))
        self.close_position(symbol)
        return [ProtectionEvent("EMERGENCY_EXIT_PENDING", symbol, "MARK_BREACH"), ProtectionEvent("CLOSED", symbol, "MARK_BREACH")]

    def _degrade(self, symbol: str, reason: str) -> list[ProtectionEvent]:
        record = self.get(symbol)
        if record.state in {ProtectionState.CLOSED, ProtectionState.DEGRADED}:
            return []
        self._save(ProtectionRecord(**{**record.to_dict(), "state": ProtectionState.DEGRADED}))
        return [ProtectionEvent("PROTECTION_FAILED", symbol, reason)]

    def check_freshness(self) -> list[ProtectionEvent]:
        events: list[ProtectionEvent] = []
        now = self.clock()
        for symbol, record in self._records.items():
            if record.state is not ProtectionState.CLOSED and not self._fresh(self._last_marks.get(symbol, record.updated_at)):
                events.extend(self._degrade(symbol, "STALE_MARK"))
        return events
