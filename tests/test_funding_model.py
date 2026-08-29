"""Realistic Bitget funding-settlement accrual (TDD: RED first).

Bitget USDT perpetuals settle funding every 8 hours at 00:00 / 08:00 / 16:00 UTC.
The previous cost model charged funding at EVERY replay bar (per-bar proxy), which
overstates funding by ~the bar-count for sub-8h holds and is not how the venue bills.
This suite defines the correct, deterministic behavior: funding is accrued only at the
actual 8h settlement timestamps that fall strictly inside a position's open interval,
direction-aware (long pays/receives opposite to short), using the per-settlement rate
(already the 8h rate, e.g. 0.0001), never a per-bar rate.

No network, no credentials, no signed calls, no orders. Pure offline measurement.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from src.evaluation.funding_model import (  # noqa: E402
    EIGHT_HOURS_MS,
    FundingLeg,
    is_settlement_timestamp,
    position_funding,
    reconcile_funding_legs,
    settlement_timestamps_in_range,
)


def _constant_mark(v: float):
    return lambda _ts: v


def _constant_rate(r: float):
    return lambda _ts: r


# --- Settlement calendar ---------------------------------------------------

def test_epoch_and_8h_boundaries_are_settlements():
    assert is_settlement_timestamp(0) is True
    assert is_settlement_timestamp(8 * 3600 * 1000) is True
    assert is_settlement_timestamp(16 * 3600 * 1000) is True
    assert is_settlement_timestamp(24 * 3600 * 1000) is True


def test_non_boundaries_are_not_settlements():
    assert is_settlement_timestamp(1 * 3600 * 1000) is False
    assert is_settlement_timestamp(4 * 3600 * 1000) is False
    assert is_settlement_timestamp(8 * 3600 * 1000 - 1) is False


def test_settlement_range_is_exclusive_start_inclusive_end():
    # (1h, 9h] -> only the 8h settlement.
    r = settlement_timestamps_in_range(1 * 3600 * 1000, 9 * 3600 * 1000)
    assert r == [8 * 3600 * 1000]
    # (0, 24h] -> 8h, 16h, 24h (three settlements).
    r2 = settlement_timestamps_in_range(0, 24 * 3600 * 1000)
    assert r2 == [8 * 3600 * 1000, 16 * 3600 * 1000, 24 * 3600 * 1000]
    # No settlement strictly inside a sub-8h window.
    r3 = settlement_timestamps_in_range(8 * 3600 * 1000 + 1, 9 * 3600 * 1000)
    assert r3 == []


# --- Direction-aware accrual ----------------------------------------------

def test_long_pays_positive_rate_receives_negative():
    net, legs = position_funding(
        "BUY", 1.0, 0, 24 * 3600 * 1000,
        _constant_mark(100.0), _constant_rate(0.0001),
    )
    # 3 settlements in (0, 24h]; long pays the positive rate each time.
    assert len(legs) == 3
    assert net == pytest.approx(3 * 1.0 * 100.0 * 0.0001)
    assert all(l.paid > 0 and l.received == 0.0 for l in legs)

    net_neg, _ = position_funding(
        "BUY", 1.0, 0, 24 * 3600 * 1000,
        _constant_mark(100.0), _constant_rate(-0.0001),
    )
    assert net_neg == pytest.approx(-3 * 1.0 * 100.0 * 0.0001)


def test_short_is_opposite_sign():
    net, legs = position_funding(
        "SELL", 1.0, 0, 24 * 3600 * 1000,
        _constant_mark(100.0), _constant_rate(0.0001),
    )
    # Short receives the positive rate (paid is negative -> received positive).
    assert net == pytest.approx(-3 * 1.0 * 100.0 * 0.0001)
    assert all(l.received > 0 and l.paid == 0.0 for l in legs)


def test_funding_only_at_settlements_not_per_bar():
    # A position held 57 one-minute bars (< 8h) crosses NO settlement, so realistic
    # funding is exactly 0, whereas a per-bar proxy would have charged 57 times.
    start = 1 * 60 * 1000
    end = start + 57 * 60 * 1000
    net, legs = position_funding(
        "BUY", 1.0, start, end,
        _constant_mark(100.0), _constant_rate(0.0002),
    )
    assert legs == []
    assert net == pytest.approx(0.0)


def test_funding_reconciles_to_leg_sum():
    net, legs = position_funding(
        "BUY", 2.0, 0, 24 * 3600 * 1000,
        _constant_mark(50.0), _constant_rate(0.0001),
    )
    assert reconcile_funding_legs(legs) == pytest.approx(net)
    assert net == pytest.approx(3 * 2.0 * 50.0 * 0.0001)


def test_position_funding_rejects_bad_side():
    with pytest.raises(ValueError):
        position_funding("HOLD", 1.0, 0, 1000, _constant_mark(1.0), _constant_rate(0.0))


def test_funding_leg_is_dataclass_with_all_fields():
    leg = FundingLeg(ts_ms=EIGHT_HOURS_MS, rate=0.0001, mark=100.0, paid=0.01, received=0.0)
    assert leg.ts_ms == EIGHT_HOURS_MS
    assert leg.paid == 0.01
