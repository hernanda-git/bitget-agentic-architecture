"""Purged holding-period label evaluation.

Produces forward-return labels for configurable holding periods
with purged chronological validation. Every label's exit index is
strictly bounded by the available history, so no future information
leaks into the current-step evaluation. This is measurement only —
it never changes the deterministic promotion gate.
"""
from __future__ import annotations


def evaluate_purged_holding_periods(
    closes: list[float],
    period: int,
    symbol: str = "BTCUSDT",
    start_ts_ms: int = 0,
) -> list[dict]:
    """Create forward-return labels over a configurable holding period
    with purged chronological validation.

    Each label contains the forward return from bar ``i`` to bar
    ``i + period``: ``closes[i + period] / closes[i] - 1``. Labels
    whose exit index exceeds the available history are dropped so
    no future information leaks into the current-step evaluation.

    The purged constraint is enforced by construction: the loop
    runs only up to ``len(closes) - period``, guaranteeing that
    every ``exit_idx`` is strictly within the available history.

    Args:
        closes: Ordered list of closing prices.
        period: Number of bars to hold. Must be positive.
        symbol: Symbol identifier for label provenance.
        start_ts_ms: Starting timestamp in milliseconds for the
            first label's entry time.

    Returns:
        List of label dicts, each with:
        - forward_return: the return from entry to exit
        - entry_idx: the index of the entry bar
        - exit_idx: the index of the exit bar (strictly < len(closes))
        - entry_ts_ms: the entry timestamp
        - exit_ts_ms: the exit timestamp
        - symbol: the symbol identifier

    Raises:
        ValueError: if period is not positive.
    """
    if period <= 0:
        raise ValueError("holding period must be positive")
    if len(closes) <= period:
        return []

    labels = []
    for i in range(len(closes) - period):
        labels.append({
            "forward_return": closes[i + period] / closes[i] - 1,
            "entry_idx": i,
            "exit_idx": i + period,
            "entry_ts_ms": start_ts_ms + i * 60_000,
            "exit_ts_ms": start_ts_ms + (i + period) * 60_000,
            "symbol": symbol,
        })
    return labels