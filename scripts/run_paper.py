"""Offline paper runner proving the decision-to-accounting path."""
from __future__ import annotations

from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger


def run_paper_once(venue: FakeExchange, ledger: EventLedger, symbol: str = "BTCUSDT") -> dict:
    ledger.append("MARKET_OBSERVED", {"symbol": symbol, "mode": "paper"})
    fill = venue.place_order("paper-open-1", symbol, "BUY", 1, 100)
    ledger.append("FILL_OBSERVED", {"client_order_id": fill.client_order_id, "fee": fill.fee})
    venue.set_protection(symbol, 95, 110)
    pos = venue.positions[symbol]
    ledger.append("PROTECTION_VERIFIED", {"symbol": symbol, "sl": pos.stop_loss, "tp": pos.take_profit})
    return {"status": "PAPER_FILLED", "fee": fill.fee, "protected": pos.stop_loss is not None and pos.take_profit is not None}
