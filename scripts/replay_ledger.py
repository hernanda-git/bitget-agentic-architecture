"""Replay an append-only paper ledger without executing anything."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def replay_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    events = list(events)
    dispositions: Counter[str] = Counter()
    positions: dict[str, dict[str, Any]] = {}
    protection: dict[str, str] = {}
    reconciliation = "UNKNOWN"
    risk_breaker = "CLOSED"
    for event in events:
        kind = event.get("event_type")
        payload = event.get("payload", {})
        if kind == "FILL_OBSERVED":
            symbol = payload.get("symbol")
            if symbol:
                quantity = float(payload.get("quantity", 0))
                side = payload.get("side")
                signed = quantity if side == "BUY" else -quantity
                current = positions.setdefault(symbol, {"quantity": 0.0, "side": side})
                current["quantity"] += signed
                current["side"] = side
                current["entry_price"] = payload.get("price")
                current["fees"] = current.get("fees", 0.0) + float(payload.get("fee", 0.0))
        elif kind in {"PROTECTION_VERIFIED", "PROTECTION_FAILED"}:
            symbol = payload.get("symbol") or _symbol_for_cycle(events, payload.get("cycle_id"))
            if symbol:
                protection[symbol] = payload.get("status", "FAILED")
                positions.setdefault(symbol, {"quantity": 0.0})["protection"] = protection[symbol]
        elif kind == "POSITION_RECONCILED":
            reconciliation = "IN_SYNC" if payload.get("in_sync") else "DEGRADED"
        elif kind == "RISK_BREAKER_OPEN":
            risk_breaker = "OPEN"
        elif kind == "RISK_BREAKER_CLOSED":
            risk_breaker = "CLOSED"
        elif kind == "CYCLE_TERMINAL":
            dispositions[str(payload.get("disposition", "UNKNOWN"))] += 1
    return {"dispositions": dict(dispositions), "positions": positions,
            "protection": protection, "reconciliation": reconciliation, "risk_breaker": risk_breaker}


def _symbol_for_cycle(events: Iterable[dict[str, Any]], cycle_id: str | None) -> str | None:
    if not cycle_id:
        return None
    for event in events:
        payload = event.get("payload", {})
        if payload.get("cycle_id") == cycle_id and payload.get("symbol"):
            return payload["symbol"]
    return None


def replay_path(path: str | Path) -> dict[str, Any]:
    from src.ledger.sqlite import EventLedger
    return replay_events(EventLedger(Path(path)).all())


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a paper EventLedger")
    parser.add_argument("ledger")
    args = parser.parse_args()
    print(json.dumps(replay_path(args.ledger), sort_keys=True))


if __name__ == "__main__":
    main()
