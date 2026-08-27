from __future__ import annotations

from typing import Any

from .models import InMemoryProtectionStore, ProtectionRecord, ProtectionState
from src.reconcile.engine import reconcile_protection


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

    def verify(self, symbol: str, venue: dict | None = None, *, bot_monitor_armed: bool = False, bot_monitor_fresh: bool = False, mark: float | None = None) -> ProtectionRecord:
        record = self.get(symbol)
        venue = venue or {}
        # Delegate to the canonical Layer 7 read-back check so the live path cannot
        # diverge from reconcile_protection (single source of truth). This also gains
        # the wrong-side-stop direction validation that the old inline logic lacked.
        result = reconcile_protection(
            intended={"stop_loss": record.stop_loss, "take_profit": record.take_profit},
            venue=venue,
            bot_side={"armed": bot_monitor_armed, "fresh": bot_monitor_fresh,
                      "stop_loss": record.stop_loss, "take_profit": record.take_profit},
            mark=mark, side=record.side,
        )
        return self._save(ProtectionRecord(**{**record.to_dict(), "state": result.state, "reasons": result.reasons}))

    def mark_unknown(self, symbol: str) -> ProtectionRecord:
        record = self.get(symbol)
        return self._save(ProtectionRecord(**{**record.to_dict(), "state": ProtectionState.UNKNOWN}))

    def close(self, symbol: str) -> ProtectionRecord:
        record = self.get(symbol)
        return self._save(ProtectionRecord(**{**record.to_dict(), "state": ProtectionState.CLOSED}))
