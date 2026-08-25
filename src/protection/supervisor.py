from __future__ import annotations

from typing import Any

from .models import InMemoryProtectionStore, ProtectionRecord, ProtectionState


class ProtectionSupervisor:
    def __init__(self, store: Any | None = None) -> None:
        self.store = store or InMemoryProtectionStore()
        self._records = {
            symbol: ProtectionRecord.from_dict(data)
            for symbol, data in self.store.load_all().items()
        }

    @property
    def entries_parked(self) -> bool:
        return any(record.state in {ProtectionState.DEGRADED, ProtectionState.UNKNOWN, ProtectionState.EMERGENCY_EXIT_PENDING} for record in self._records.values())

    def _save(self, record: ProtectionRecord) -> ProtectionRecord:
        self._records[record.symbol] = record
        self.store.save(record)
        return record

    def register_position(self, symbol: str, side: str, quantity: float, stop_loss: float | None, take_profit: float | None) -> ProtectionRecord:
        return self._save(ProtectionRecord(symbol, side.upper(), quantity, stop_loss, take_profit))

    def get(self, symbol: str) -> ProtectionRecord:
        return self._records[symbol]

    def verify(self, symbol: str, venue: dict | None = None, *, bot_monitor_armed: bool = False, bot_monitor_fresh: bool = False) -> ProtectionRecord:
        record = self.get(symbol)
        venue = venue or {}
        venue_ok = (venue.get("stop_loss") is not None and venue.get("take_profit") is not None and
                    venue.get("stop_loss") == record.stop_loss and venue.get("take_profit") == record.take_profit)
        bot_ok = (record.stop_loss is not None and record.take_profit is not None and
                  bot_monitor_armed and bot_monitor_fresh)
        if venue_ok or bot_ok:
            state = ProtectionState.PROTECTED
        elif venue.get("stop_loss") is None or venue.get("take_profit") is None:
            state = ProtectionState.DEGRADED
        else:
            state = ProtectionState.UNKNOWN
        return self._save(ProtectionRecord(**{**record.to_dict(), "state": state}))

    def mark_unknown(self, symbol: str) -> ProtectionRecord:
        record = self.get(symbol)
        return self._save(ProtectionRecord(**{**record.to_dict(), "state": ProtectionState.UNKNOWN}))

    def close(self, symbol: str) -> ProtectionRecord:
        record = self.get(symbol)
        return self._save(ProtectionRecord(**{**record.to_dict(), "state": ProtectionState.CLOSED}))
