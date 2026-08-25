"""Fee-inclusive realized trade accounting."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class TradeAccounting:
    gross_pnl: float
    entry_fee: float
    exit_fee: float
    funding_paid: float
    funding_received: float
    slippage_cost: float
    net_pnl: float
    return_on_margin: float

def calculate_trade(*, side: str, quantity: float, entry_price: float, exit_price: float,
                    entry_fee: float, exit_fee: float, funding_paid: float,
                    funding_received: float, slippage_cost: float, margin: float) -> TradeAccounting:
    direction = 1 if side.upper() in {"BUY", "LONG"} else -1
    gross = direction * (exit_price - entry_price) * quantity
    net = gross - entry_fee - exit_fee - funding_paid + funding_received - slippage_cost
    return TradeAccounting(gross, entry_fee, exit_fee, funding_paid, funding_received,
                           slippage_cost, net, net / margin if margin else 0.0)
