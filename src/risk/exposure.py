"""Portfolio-level exposure gates. These are pure and network-free."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Iterable

from .portfolio import PositionSnapshot


@dataclass(frozen=True)
class ExposureLimits:
    max_gross_notional: float
    max_net_notional: float
    max_correlated_notional: float
    max_symbol_notional: float
    correlations: dict[str, dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value in (self.max_gross_notional, self.max_net_notional,
                      self.max_correlated_notional, self.max_symbol_notional):
            if not isfinite(value) or value <= 0:
                raise ValueError("exposure limits must be finite and positive")


@dataclass(frozen=True)
class ExposureResult:
    allowed: bool
    code: str = "APPROVED"
    gross_notional: float = 0.0
    net_notional: float = 0.0
    correlated_notional: float = 0.0
    symbol_notional: float = 0.0


def _correlation(a: str, b: str, matrix: dict[str, dict[str, float]]) -> float:
    return float(matrix.get(a, {}).get(b, matrix.get(b, {}).get(a, 0.0)))


def check_exposure(symbol: str, side: str, notional: float,
                   positions: Iterable[PositionSnapshot], limits: ExposureLimits) -> ExposureResult:
    if notisfinite := (not isfinite(notional) or notional <= 0):
        raise ValueError("notional must be finite and positive")
    current = list(positions)
    symbol_total = notional + sum(p.notional for p in current if p.symbol == symbol)
    gross = notional + sum(p.notional for p in current)
    signed = notional if side in {"BUY", "LONG"} else -notional
    net = signed + sum(p.signed_notional for p in current)
    correlated = notional + sum(p.notional * abs(_correlation(symbol, p.symbol, limits.correlations))
                                 for p in current)
    values = (gross, abs(net), correlated, symbol_total)
    codes = ("GROSS_EXPOSURE_LIMIT", "NET_EXPOSURE_LIMIT", "CORRELATED_EXPOSURE_LIMIT", "SYMBOL_CONCENTRATION_LIMIT")
    bounds = (limits.max_gross_notional, limits.max_net_notional,
              limits.max_correlated_notional, limits.max_symbol_notional)
    for value, bound, code in zip(values, bounds, codes):
        if value >= bound:
            return ExposureResult(False, code, gross, net, correlated, symbol_total)
    return ExposureResult(True, "APPROVED", gross, net, correlated, symbol_total)
