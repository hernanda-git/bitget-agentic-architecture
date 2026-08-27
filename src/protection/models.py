from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class ProtectionState(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    PROTECTED = "PROTECTED"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    EMERGENCY_EXIT_PENDING = "EMERGENCY_EXIT_PENDING"
    CLOSED = "CLOSED"


@dataclass
class ProtectionRecord:
    symbol: str
    side: str
    quantity: float
    stop_loss: float | None
    take_profit: float | None
    state: ProtectionState = ProtectionState.PENDING
    reasons: tuple[str, ...] = ()
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProtectionRecord":
        data = dict(data)
        data["state"] = ProtectionState(data["state"])
        data.setdefault("reasons", ())
        return cls(**data)


class InMemoryProtectionStore:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def load_all(self) -> dict[str, dict[str, Any]]:
        return dict(self._records)

    def save(self, record: ProtectionRecord) -> None:
        self._records[record.symbol] = record.to_dict()


class JsonProtectionStore(InMemoryProtectionStore):
    """Small atomic JSON store suitable for the standalone demo."""
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                self._records = json.load(handle)

    def save(self, record: ProtectionRecord) -> None:
        super().save(record)
        directory = os.path.dirname(os.path.abspath(self.path))
        fd, temp_path = tempfile.mkstemp(prefix=".protection-", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._records, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
