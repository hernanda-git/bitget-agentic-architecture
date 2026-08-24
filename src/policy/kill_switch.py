"""Durable kill switch independent from the model/provider."""
from __future__ import annotations

import json
import os
from pathlib import Path


class KillSwitch:
    def __init__(self, path: Path) -> None:
        self.path = path

    def is_active(self) -> bool:
        if not self.path.exists():
            return True
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return True
        return bool(data.get("active", True))

    def activate(self, reason: str) -> None:
        self._write({"active": True, "reason": reason})

    def clear(self, authorization: str) -> None:
        if authorization != "EXPLICIT_OPERATOR_CLEAR":
            raise PermissionError("kill switch clear requires explicit operator authorization")
        self._write({"active": False, "reason": "cleared"})

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(data, sort_keys=True) + "\n")
        temp.replace(self.path)
