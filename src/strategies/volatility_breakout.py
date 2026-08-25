from __future__ import annotations
from src.features.technical import build_features
from src.strategies.base import CostAssumptions, Candidate, make_candidate

def generate_volatility_breakout(snapshot, costs: CostAssumptions = CostAssumptions()) -> list[Candidate]:
    f = build_features(snapshot); price = snapshot.mark_price; high = f["range_high"].value
    if price < high * 0.995: return []
    move = max(price * 0.004, f["volatility"].value * price * 2)
    c = make_candidate(name="volatility_breakout", version="breakout-v1", snapshot=snapshot, side="BUY", entry=snapshot.ask,
                       stop=price - move * .7, target=price + move, expiry=snapshot.source_ts_ms + 120_000,
                       expected_move=move, costs=costs, regime="HIGH_VOLATILITY")
    return [c] if c else []
