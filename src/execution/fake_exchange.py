"""Deterministic, event-driven paper exchange. It never opens a network connection."""
from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any
from src.accounting.pnl import calculate_trade
from src.execution.specifications import FeeSchedule, FundingSchedule, VenueSpecification, VenueRuleError
from src.evaluation.funding_model import is_settlement_timestamp, settlement_funding_leg


def _per_bar_funding(side: str, quantity: float, mark: float, rate: float) -> tuple[float, float]:
    """Conservative per-bar funding proxy (direction-aware).

    Used only when a market event is NOT at a real 8h settlement boundary (e.g. the
    synthetic ``real_funding=False`` stress path, whose swap-stress proxy deliberately
    overstates funding as a conservative upper bound). The settlement-accurate path
    (``apply_funding_settlement``) uses the shared funding model instead. Kept as a
    separate helper so the two accrual paths can be tested and mutated independently.
    """
    if side == "BUY":
        paid = max(quantity * mark * rate, 0.0)
        received = max(-quantity * mark * rate, 0.0)
    else:
        received = max(quantity * mark * rate, 0.0)
        paid = max(-quantity * mark * rate, 0.0)
    return paid, received

class OrderStatus(str, Enum):
    NEW="NEW"; PARTIALLY_FILLED="PARTIALLY_FILLED"; FILLED="FILLED"; CANCEL_REQUESTED="CANCEL_REQUESTED"; CANCELLED="CANCELLED"; REJECTED="REJECTED"; EXPIRED="EXPIRED"

class CloseReason(str, Enum):
    END_OF_REPLAY = "END_OF_REPLAY"

@dataclass(frozen=True)
class OrderRequest:
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    price: float | None
    time_in_force: str = "GTC"
    reduce_only: bool = False
    leverage: float = 1
    margin_mode: str = "isolated"
    close_reason: CloseReason | None = None

@dataclass(frozen=True)
class FakeOrder:
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    price: float | None
    status: OrderStatus
    filled_quantity: float = 0.0
    reason: str = ""
    reduce_only: bool = False
    close_reason: CloseReason | None = None

@dataclass(frozen=True)
class FakeFill:
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float
    funding: float = 0.0
    slippage_cost: float = 0.0
    spread_cost: float = 0.0

@dataclass(frozen=True)
class FakePosition:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    entry_reference_price: float | None = None
    entry_spread_cost: float = 0.0
    entry_slippage_cost: float = 0.0
    funding_paid: float = 0.0
    funding_received: float = 0.0

@dataclass(frozen=True)
class ExchangeEvent:
    kind: str
    symbol: str
    client_order_id: str | None = None
    price: float | None = None

class FakeExchange:
    def __init__(self, fee_bps: float = 5.0, *, venue: VenueSpecification | None = None,
                 initial_balance: float = 10_000.0, slippage_bps: float = 0.0,
                 partial_fill_ratio: float = 0.5):
        self.venue = venue or VenueSpecification(0.01, 0.001, 0.001, 1.0, 1.0,
            FeeSchedule(fee_bps, fee_bps), FundingSchedule(0.0), 20, frozenset({"isolated", "cross"}))
        self.fee_bps, self.slippage_bps = fee_bps, slippage_bps
        self.partial_fill_ratio = partial_fill_ratio
        self.balance = float(initial_balance)
        self.orders: dict[str, FakeOrder] = {}; self.fills: list[FakeFill] = []
        self.positions: dict[str, FakePosition] = {}; self.closed_trades: list[dict[str, Any]] = []
        self.market_prices: dict[str, tuple[float, float, float]] = {}
        self._last_sequence: dict[str, int] = {}
        self._funding_paid = 0.0; self._funding_received = 0.0

    def _price(self, symbol, side, requested=None):
        bid, ask, mark = self.market_prices.get(symbol, (100.0, 100.0, 100.0))
        base = ask if side == "BUY" else bid
        if requested is None: return base * (1 + (1 if side == "BUY" else -1) * self.slippage_bps / 10000)
        return requested

    def submit_order(self, request: OrderRequest) -> FakeOrder:
        if request.client_order_id in self.orders:
            old = self.orders[request.client_order_id]
            if old.symbol == request.symbol and old.side == request.side and old.quantity == request.quantity: return old
            raise ValueError("duplicate client order id")
        try: self.venue.validate_order(symbol=request.symbol, quantity=request.quantity, price=request.price or 100.0, leverage=request.leverage, margin_mode=request.margin_mode)
        except VenueRuleError as exc:
            order = FakeOrder(request.client_order_id, request.symbol, request.side, request.quantity, request.price, OrderStatus.REJECTED, reason=str(exc), reduce_only=request.reduce_only, close_reason=request.close_reason)
            self.orders[request.client_order_id] = order; return order
        existing = self.positions.get(request.symbol)
        if request.reduce_only and (not existing or existing.side == request.side or request.quantity > existing.quantity):
            order = FakeOrder(request.client_order_id, request.symbol, request.side, request.quantity, request.price, OrderStatus.REJECTED, reason="REDUCE_ONLY_NO_POSITION", reduce_only=True)
            self.orders[request.client_order_id] = order; return order
        bid, ask, _ = self.market_prices.get(request.symbol, (100.0, 100.0, 100.0))
        crosses = request.price is None or (request.side == "BUY" and request.price >= ask) or (request.side == "SELL" and request.price <= bid)
        if not crosses:
            status = OrderStatus.EXPIRED if request.time_in_force in {"IOC", "FOK"} else OrderStatus.NEW
            order = FakeOrder(request.client_order_id, request.symbol, request.side, request.quantity, request.price, status, reduce_only=request.reduce_only, close_reason=request.close_reason)
            self.orders[request.client_order_id] = order; return order
        qty = request.quantity
        price = self._price(request.symbol, request.side, request.price)
        order = FakeOrder(request.client_order_id, request.symbol, request.side, qty, price, OrderStatus.FILLED, qty, reduce_only=request.reduce_only, close_reason=request.close_reason)
        self.orders[request.client_order_id] = order; self._fill(order, qty, price)
        return self.orders[request.client_order_id]

    def place_order(self, client_order_id, symbol, side, quantity, price):
        # Compatibility facade is an immediate paper fill, matching the legacy
        # unit API. New code should use submit_order and market events.
        order = self.submit_order(OrderRequest(client_order_id, symbol, side, quantity, None))
        fills = self.read_fills(client_order_id)
        if not fills: raise ValueError(order.reason or "order not filled")
        return fills[-1]

    def _fill(self, order, quantity, price):
        fee = quantity * price * self.fee_bps / 10000
        bid, ask, mark = self.market_prices.get(order.symbol, (price, price, price))
        quoted = ask if order.side == "BUY" else bid
        spread_cost = abs(quoted - mark) * quantity
        slippage_cost = abs(price - quoted) * quantity
        fill = FakeFill(order.client_order_id, order.symbol, order.side, quantity, price, fee,
                        0.0, slippage_cost, spread_cost)
        self.fills.append(fill); self._apply_position(order, quantity, price, fee)

    def _apply_position(self, order, quantity, price, fee):
        old = self.positions.get(order.symbol)
        if old and old.side != order.side:
            close_qty = min(old.quantity, quantity)
            reference_price = self.market_prices.get(order.symbol, (price, price, price))[2]
            entry_reference_price = old.entry_reference_price if old.entry_reference_price is not None else old.entry_price
            gross = (reference_price - entry_reference_price) * close_qty * (1 if old.side == "BUY" else -1)
            entry_fee = old.entry_price * close_qty * self.fee_bps / 10000
            fill = self.fills[-1]
            ratio = close_qty / old.quantity
            funding_paid = old.funding_paid * ratio
            funding_received = old.funding_received * ratio
            funding = funding_paid - funding_received
            spread_cost = old.entry_spread_cost * ratio + fill.spread_cost
            slippage_cost = old.entry_slippage_cost * ratio + fill.slippage_cost
            self.closed_trades.append({"symbol": order.symbol, "status": "CLOSED", "gross_pnl": gross, "entry_fee": entry_fee, "exit_fee": fee, "funding": funding, "spread_cost": spread_cost, "slippage_cost": slippage_cost, "net_pnl": gross-entry_fee-fee-funding-spread_cost-slippage_cost, "close_reason": order.close_reason.value if order.close_reason else None, "reduce_only": order.reduce_only})
            rem = old.quantity - close_qty
            if rem <= 1e-12: self.positions.pop(order.symbol, None)
            else: self.positions[order.symbol] = replace(old, quantity=rem,
                                                         entry_spread_cost=old.entry_spread_cost * (1 - ratio),
                                                         entry_slippage_cost=old.entry_slippage_cost * (1 - ratio),
                                                         funding_paid=old.funding_paid * (1 - ratio),
                                                         funding_received=old.funding_received * (1 - ratio))
            if quantity <= old.quantity: return
            quantity -= old.quantity
        if old and old.side == order.side:
            total = old.quantity + quantity; avg = (old.entry_price*old.quantity + price*quantity)/total
            reference_price = self.market_prices.get(order.symbol, (price, price, price))[2]
            old_reference = old.entry_reference_price if old.entry_reference_price is not None else old.entry_price
            entry_fill = self.fills[-1]
            self.positions[order.symbol] = replace(old, quantity=total, entry_price=avg,
                                                   entry_reference_price=(old_reference * old.quantity + reference_price * quantity) / total,
                                                   entry_spread_cost=old.entry_spread_cost + entry_fill.spread_cost,
                                                   entry_slippage_cost=old.entry_slippage_cost + entry_fill.slippage_cost)
        else:
            reference_price = self.market_prices.get(order.symbol, (price, price, price))[2]
            fill = self.fills[-1]
            self.positions[order.symbol] = FakePosition(order.symbol, order.side, quantity, price,
                                                        entry_reference_price=reference_price,
                                                        entry_spread_cost=fill.spread_cost,
                                                        entry_slippage_cost=fill.slippage_cost)

    def cancel_order(self, client_order_id):
        order = self.orders[client_order_id]
        if order.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}: return order
        self.orders[client_order_id] = replace(order, status=OrderStatus.CANCEL_REQUESTED)
        self.orders[client_order_id] = replace(self.orders[client_order_id], status=OrderStatus.CANCELLED)
        return self.orders[client_order_id]

    def read_order(self, client_order_id): return self.orders[client_order_id]
    def read_fills(self, client_order_id=None): return [f for f in self.fills if client_order_id is None or f.client_order_id == client_order_id]
    def read_positions(self, symbol=None): return [p for s,p in self.positions.items() if symbol is None or s == symbol]
    def read_open_orders(self): return [o for o in self.orders.values() if o.status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCEL_REQUESTED}]
    def read_balance(self): return {"equity": self.balance, "fees": sum(f.fee for f in self.fills), "funding_paid": self._funding_paid, "funding_received": self._funding_received}

    def set_protection(self, symbol, stop_loss, take_profit):
        position = self.positions[symbol]
        self.positions[symbol] = replace(position, stop_loss=stop_loss, take_profit=take_profit)

    def apply_funding_settlement(self, symbol: str, mark: float, rate: float) -> None:
        """Accrue funding at one real 8h Bitget settlement using the shared model.

        Delegates the direction-aware (paid, received) math to
        ``settlement_funding_leg`` so the exchange cannot drift from
        ``position_funding``'s verified behavior. Only call this when the event
        timestamp is an actual settlement boundary (see ``apply_market_event``).
        """
        for p in self.read_positions(symbol):
            paid, received = settlement_funding_leg(p.side, p.quantity, mark, rate)
            self._funding_paid += paid
            self._funding_received += received
            self.positions[symbol] = replace(
                p,
                funding_paid=p.funding_paid + paid,
                funding_received=p.funding_received + received,
            )

    def close_position_at_end_of_replay(self, symbol: str, final_mark: float, client_order_id: str) -> FakeOrder:
        """Close the remaining paper position at the final executable quote."""
        position = self.positions.get(symbol)
        if position is None:
            return self.submit_order(OrderRequest(client_order_id, symbol, "BUY", 0.0, None, reduce_only=True, close_reason=CloseReason.END_OF_REPLAY))
        bid, ask, _ = self.market_prices.get(symbol, (final_mark, final_mark, final_mark))
        self.market_prices[symbol] = (bid, ask, final_mark)
        side = "SELL" if position.side == "BUY" else "BUY"
        return self.submit_order(OrderRequest(client_order_id, symbol, side, position.quantity, None,
                                              reduce_only=True, close_reason=CloseReason.END_OF_REPLAY))

    def apply_market_event(self, event):
        previous = self._last_sequence.get(event.symbol, -1)
        if event.sequence <= previous: return []
        self._last_sequence[event.symbol] = event.sequence
        self.market_prices[event.symbol] = (event.bid, event.ask, event.mark)
        if event.funding_rate:
            # Realistic Bitget funding accrual: funding settles only at the venue's
            # 8h UTC boundaries. When the event timestamp is an actual settlement,
            # delegate the direction-aware accrual to the shared funding model so the
            # accounting matches `position_funding` exactly (one leg, no per-bar proxy).
            # A non-settlement timestamp (e.g. a synthetic replay bar with no real
            # settlement time, or the conservative real_funding=False stress path)
            # keeps the flat per-bar proxy as a conservative upper bound. The model
            # is the source of truth for settlement-accurate cost; the proxy is a
            # stress over-estimate that can never be smaller than the real venue bill.
            if is_settlement_timestamp(event.timestamp_ms):
                self.apply_funding_settlement(event.symbol, event.mark, event.funding_rate)
            else:
                for p in self.read_positions(event.symbol):
                    paid, received = _per_bar_funding(p.side, p.quantity, event.mark, event.funding_rate)
                    self._funding_paid += paid
                    self._funding_received += received
                    self.positions[event.symbol] = replace(
                        p,
                        funding_paid=p.funding_paid + paid,
                        funding_received=p.funding_received + received,
                    )
        events = []
        for oid, order in list(self.orders.items()):
            if order.symbol != event.symbol or order.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}: continue
            crosses = (order.side == "BUY" and order.price is not None and order.price >= event.ask) or (order.side == "SELL" and order.price is not None and order.price <= event.bid)
            if crosses:
                remaining = order.quantity - order.filled_quantity
                qty = remaining if order.status is OrderStatus.PARTIALLY_FILLED else (remaining * self.partial_fill_ratio if remaining > 0 and self.partial_fill_ratio < 1 else remaining)
                status = OrderStatus.FILLED if qty >= remaining-1e-12 else OrderStatus.PARTIALLY_FILLED
                self.orders[oid] = replace(order, status=status, filled_quantity=order.filled_quantity+qty)
                self._fill(self.orders[oid], qty, order.price); events.append(ExchangeEvent("ORDER_FILLED", event.symbol, oid, order.price))
        p = self.positions.get(event.symbol)
        breach = False
        if p and p.side == "BUY":
            breach = event.mark <= (p.stop_loss if p.stop_loss is not None else float("-inf")) or event.mark >= (p.take_profit if p.take_profit is not None else float("inf"))
        elif p and p.side == "SELL":
            breach = event.mark >= (p.stop_loss if p.stop_loss is not None else float("inf")) or event.mark <= (p.take_profit if p.take_profit is not None else float("-inf"))
        if p and breach:
            oid = f"protection-{event.symbol}-{event.sequence}"
            side = "SELL" if p.side == "BUY" else "BUY"
            price = self._price(event.symbol, side)
            order = FakeOrder(oid, event.symbol, side, p.quantity, price, OrderStatus.FILLED, p.quantity)
            self._fill(order, p.quantity, price)
            self.orders[oid] = order
            events.append(ExchangeEvent("PROTECTION_TRIGGERED", event.symbol, oid, price))
        return events

    def read_state(self): return {"orders": dict(self.orders), "fills": list(self.fills), "positions": dict(self.positions)}
