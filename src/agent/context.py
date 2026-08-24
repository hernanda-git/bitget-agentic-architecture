"""Bounded, hashed context passed to an autonomous provider."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from src.market.models import MarketSnapshot
from src.providers.ports import AgentContext


@dataclass(frozen=True)
class PortfolioView:
    positions: tuple[dict[str, Any], ...] = ()
    open_orders: tuple[dict[str, Any], ...] = ()
    realized_pnl_usd: float = 0.0
    fees_usd: float = 0.0


def build_context(snapshot: MarketSnapshot, portfolio: PortfolioView,
                  policy_view: dict[str, Any], recent_events: tuple[dict[str, Any], ...] = ()) -> AgentContext:
    if len(recent_events) > 50:
        recent_events = recent_events[-50:]
    raw = {
        "snapshot": snapshot.canonical(),
        "portfolio": {
            "positions": portfolio.positions,
            "open_orders": portfolio.open_orders,
            "realized_pnl_usd": portfolio.realized_pnl_usd,
            "fees_usd": portfolio.fees_usd,
        },
        "policy_view": policy_view,
        "recent_events": recent_events,
    }
    context_id = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return AgentContext(context_id, raw["snapshot"], raw["portfolio"], raw["policy_view"], recent_events)
