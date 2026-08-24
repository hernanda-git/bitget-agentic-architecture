"""Deterministic paper exchange. No network and no credentials."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FakeOrder:
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    status: str

@dataclass(frozen=True)
class FakeFill:
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float

@dataclass(frozen=True)
class FakePosition:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None

class FakeExchange:
    def __init__(self, fee_bps: float = 5.0):
        self.fee_bps = fee_bps
        self.orders: dict[str, FakeOrder] = {}
        self.fills: list[FakeFill] = []
        self.positions: dict[str, FakePosition] = {}

    def place_order(self, client_order_id: str, symbol: str, side: str, quantity: float, price: float) -> FakeFill:
        if client_order_id in self.orders:
            existing = [f for f in self.fills if f.client_order_id == client_order_id]
            if existing:
                return existing[0]
            raise ValueError("duplicate order without fill")
        if quantity <= 0 or price <= 0 or side not in {"BUY", "SELL"}:
            raise ValueError("invalid order")
        self.orders[client_order_id] = FakeOrder(client_order_id, symbol, side, quantity, price, "FILLED")
        fee = quantity * price * self.fee_bps / 10_000
        fill = FakeFill(client_order_id, symbol, side, quantity, price, fee)
        self.fills.append(fill)
        existing = self.positions.get(symbol)
        if existing and existing.side != side:
            remaining = existing.quantity - quantity
            if remaining <= 0:
                self.positions.pop(symbol, None)
            else:
                self.positions[symbol] = FakePosition(symbol, existing.side, remaining, existing.entry_price, existing.stop_loss, existing.take_profit)
        else:
            self.positions[symbol] = FakePosition(symbol, side, quantity, price)
        return fill

    def set_protection(self, symbol: str, stop_loss: float, take_profit: float) -> None:
        position = self.positions[symbol]
        self.positions[symbol] = FakePosition(position.symbol, position.side, position.quantity, position.entry_price, stop_loss, take_profit)

    def read_state(self) -> dict:
        return {"orders": dict(self.orders), "fills": list(self.fills), "positions": dict(self.positions)}
