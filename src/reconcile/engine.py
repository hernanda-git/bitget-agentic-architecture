"""Venue/local state reconciliation and protection checks."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ReconcileResult:
    in_sync: bool
    reasons: tuple[str,...]

def reconcile_positions(local: dict, venue: dict) -> ReconcileResult:
    reasons=[]
    if set(local) != set(venue): reasons.append('POSITION_SYMBOL_DRIFT')
    for symbol in set(local)&set(venue):
        if local[symbol] != venue[symbol]: reasons.append(f'POSITION_DRIFT:{symbol}')
    return ReconcileResult(not reasons, tuple(reasons))

def verify_protection(position: dict) -> tuple[bool,str]:
    if not position.get('symbol'): return False,'NO_SYMBOL'
    if position.get('quantity',0)<=0: return False,'NO_OPEN_POSITION'
    if position.get('stop_loss') is None: return False,'STOP_LOSS_MISSING'
    if position.get('take_profit') is None: return False,'TAKE_PROFIT_MISSING'
    return True,'PROTECTED'
