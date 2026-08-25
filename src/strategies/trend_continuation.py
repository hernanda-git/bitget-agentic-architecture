from __future__ import annotations
from src.features.technical import build_features
from src.strategies.base import CostAssumptions, Candidate, make_candidate

def generate_trend_continuation(snapshot, costs: CostAssumptions = CostAssumptions()) -> list[Candidate]:
    f = build_features(snapshot); price = snapshot.mark_price; momentum = f["momentum"].value
    if momentum <= 0: return []
    move = abs(momentum) * 0.5
    c = make_candidate(name="trend_continuation", version="trend-v1", snapshot=snapshot, side="BUY", entry=snapshot.ask,
                       stop=price - max(move * 0.8, price * .002), target=price + move, expiry=snapshot.source_ts_ms + 300_000,
                       expected_move=move, costs=costs, regime="TRENDING")
    return [c] if c else []
