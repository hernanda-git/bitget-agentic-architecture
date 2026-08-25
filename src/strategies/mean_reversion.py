from __future__ import annotations
from src.features.technical import build_features
from src.strategies.base import CostAssumptions, Candidate, make_candidate

def generate_mean_reversion(snapshot, costs: CostAssumptions = CostAssumptions()) -> list[Candidate]:
    f = build_features(snapshot); price = snapshot.mark_price; deviation = f["sma"].value - price
    if deviation <= 0: return []
    move = abs(deviation) * 0.7
    c = make_candidate(name="mean_reversion", version="mean-reversion-v1", snapshot=snapshot, side="BUY", entry=snapshot.ask,
                       stop=price - max(move, price * .002), target=price + move, expiry=snapshot.source_ts_ms + 180_000,
                       expected_move=move, costs=costs, regime="RANGING")
    return [c] if c else []
