"""Replay an append-only paper ledger without executing anything."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ReplayMismatch(ValueError):
    """Raised when durable runtime state cannot be reproduced by replay."""


def _numeric(value: Any) -> float:
    return round(float(value), 12)


def assert_replay_equal(expected: dict[str, Any], replayed: dict[str, Any]) -> None:
    for field in ("dispositions", "positions", "protection", "reconciliation", "risk_breaker", "closed_trades"):
        if expected.get(field) != replayed.get(field):
            raise ReplayMismatch(f"replay mismatch in {field}")
    for field in ("fees", "funding", "net_pnl"):
        if _numeric(expected.get(field, 0)) != _numeric(replayed.get(field, 0)):
            raise ReplayMismatch(f"replay mismatch in {field}")


def replay_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    events = list(events)
    dispositions: Counter[str] = Counter()
    positions: dict[str, dict[str, Any]] = {}
    protection: dict[str, str] = {}
    reconciliation = "UNKNOWN"
    risk_breaker = "CLOSED"
    closed_trades = []
    net_pnl = 0.0
    fees = 0.0
    funding = 0.0
    fill_funding_seen = False
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
                fees += float(payload.get("fee", 0.0))
                funding += float(payload.get("funding", 0.0))
                fill_funding_seen = fill_funding_seen or "funding" in payload
        elif kind in {"PROTECTION_VERIFIED", "PROTECTION_FAILED"}:
            symbol = payload.get("symbol") or _symbol_for_cycle(events, payload.get("cycle_id"))
            if symbol:
                protection[symbol] = payload.get("status", "FAILED")
                positions.setdefault(symbol, {"quantity": 0.0})["protection"] = protection[symbol]
        elif kind == "POSITION_RECONCILED":
            reconciliation = "IN_SYNC" if payload.get("in_sync") else "DEGRADED"
        elif kind == "TRADE_CLOSED":
            closed_trades.append(payload)
            net_pnl += float(payload.get("net_pnl", 0.0))
            if not fill_funding_seen:
                funding += float(payload.get("funding", 0.0))
        elif kind == "RISK_BREAKER_OPEN":
            risk_breaker = "OPEN"
        elif kind == "RISK_BREAKER_CLOSED":
            risk_breaker = "CLOSED"
        elif kind == "CYCLE_TERMINAL":
            dispositions[str(payload.get("disposition", "UNKNOWN"))] += 1
    return {"dispositions": dict(dispositions), "positions": {symbol: position for symbol, position in positions.items() if abs(float(position.get("quantity", 0))) > 1e-12},
            "open_positions": [p for p in positions.values() if abs(float(p.get("quantity", 0))) > 1e-12],
            "closed_trades": closed_trades, "net_pnl": net_pnl, "fees": fees, "funding": funding,
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
