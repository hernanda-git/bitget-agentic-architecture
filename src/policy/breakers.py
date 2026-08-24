"""Persistent, model-independent entry circuit breakers."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

BREAKER_NAMES = (
    "provider", "market_data", "rate_limit", "reconciliation",
    "protection", "daily_loss", "drawdown", "heartbeat",
)


class BreakerStore:
    """Small injectable JSON store, suitable for tests or a local runtime."""
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, data: Mapping[str, Mapping[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, sort_keys=True) + "\n")
        tmp.replace(self.path)


class BreakerRegistry:
    def __init__(self, store: BreakerStore) -> None:
        self.store = store
        self._state = store.load()

    def _check_name(self, name: str) -> None:
        if name not in BREAKER_NAMES:
            raise ValueError(f"unknown breaker: {name}")

    def trip(self, name: str, reason: str) -> None:
        self._check_name(name)
        self._state[name] = {"reason": str(reason)}
        self.store.save(self._state)

    def clear(self, name: str, *, actor: str) -> None:
        self._check_name(name)
        if actor != "operator":
            raise PermissionError("only operator may clear breakers")
        self._state.pop(name, None)
        self.store.save(self._state)

    def is_open(self, name: str) -> bool:
        self._check_name(name)
        return name in self._state

    def entries_parked(self) -> bool:
        return bool(self._state)

    def reason_codes(self) -> list[str]:
        return sorted(f"{name.upper()}_BREAKER" for name in self._state)

    def snapshot(self) -> dict[str, dict[str, str]]:
        return dict(self._state)


# Public alias for callers using circuit terminology.
CircuitBreakers = BreakerRegistry
