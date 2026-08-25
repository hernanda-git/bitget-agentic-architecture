from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class CostAssumptions:
    fee_bps: float = 5.0
    funding_bps: float = 1.0
    slippage_bps: float = 2.0
    spread_bps: float | None = None

@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    strategy_name: str
    strategy_version: str
    symbol: str
    side: Literal["BUY", "SELL"]
    entry: float
    stop_loss: float
    take_profit: float
    expiry: int
    feature_snapshot_hash: str
    expected_cost: float
    minimum_required_edge: float
    expected_move: float
    regime: str = ""

    def __post_init__(self) -> None:
        if self.entry <= 0 or self.stop_loss <= 0 or self.take_profit <= 0:
            raise ValueError("candidate prices must be positive")
        if self.expected_move <= self.expected_cost:
            raise ValueError("candidate edge does not exceed expected cost")
        if self.minimum_required_edge < self.expected_cost:
            raise ValueError("minimum edge cannot be below expected cost")

def cost_fraction(snapshot, costs: CostAssumptions) -> float:
    spread_bps = costs.spread_bps if costs.spread_bps is not None else snapshot.spread_bps
    return (2 * costs.fee_bps + costs.funding_bps + spread_bps + costs.slippage_bps) / 10_000

def make_candidate(*, name, version, snapshot, side, entry, stop, target, expiry, expected_move, costs, regime=""):
    expected_cost = entry * cost_fraction(snapshot, costs)
    minimum = expected_cost * 1.05
    if expected_move <= expected_cost:
        return None
    digest = (snapshot.snapshot_hash or snapshot.computed_hash())[:16]
    return Candidate(f"{name}-{snapshot.symbol}-{snapshot.source_ts_ms}-{side}", name, version, snapshot.symbol, side,
                     entry, stop, target, expiry, snapshot.snapshot_hash or snapshot.computed_hash(), expected_cost, minimum,
                     expected_move, regime)
