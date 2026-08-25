"""Account and portfolio facts used by deterministic risk policy."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float = 0.0

    @property
    def notional(self) -> float:
        return self.quantity * self.mark_price

    @property
    def signed_notional(self) -> float:
        return self.notional if self.side in {"BUY", "LONG"} else -self.notional


@dataclass(frozen=True)
class PortfolioSnapshot:
    equity: float
    available_margin: float
    used_margin: float
    gross_notional: float
    net_notional: float
    long_notional: float
    short_notional: float
    positions_by_symbol: dict[str, PositionSnapshot] = field(default_factory=dict)
    realized_daily_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees_today: float = 0.0
    funding_today: float = 0.0
    peak_equity: float = 0.0
    drawdown: float = 0.0

    def __post_init__(self) -> None:
        for name in ("equity", "available_margin", "used_margin", "gross_notional", "net_notional",
                     "long_notional", "short_notional", "realized_daily_pnl", "unrealized_pnl",
                     "fees_today", "funding_today", "peak_equity", "drawdown"):
            value = float(getattr(self, name))
            if value != value or value in {float("inf"), float("-inf")}:
                raise ValueError(f"{name} must be finite")
        if self.equity < 0 or self.available_margin < 0 or self.used_margin < 0:
            raise ValueError("account values cannot be negative")

    @classmethod
    def from_positions(cls, *, equity: float, available_margin: float, used_margin: float,
                       positions: Iterable[PositionSnapshot], realized_daily_pnl: float = 0.0,
                       fees_today: float = 0.0, funding_today: float = 0.0,
                       peak_equity: float | None = None) -> "PortfolioSnapshot":
        by_symbol = {p.symbol: p for p in positions}
        long = sum(p.notional for p in by_symbol.values() if p.side in {"BUY", "LONG"})
        short = sum(p.notional for p in by_symbol.values() if p.side in {"SELL", "SHORT"})
        peak = max(float(equity), float(peak_equity if peak_equity is not None else equity))
        return cls(float(equity), float(available_margin), float(used_margin), long + short,
                   long - short, long, short, by_symbol,
                   float(realized_daily_pnl), sum(p.unrealized_pnl for p in by_symbol.values()),
                   float(fees_today), float(funding_today), peak, peak - float(equity))

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["positions_by_symbol"] = {k: asdict(v) for k, v in self.positions_by_symbol.items()}
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PortfolioSnapshot":
        raw = dict(value)
        positions = {k: PositionSnapshot(**v) for k, v in raw.pop("positions_by_symbol", {}).items()}
        return cls(positions_by_symbol=positions, **raw)
