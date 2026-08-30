"""Ledger reconciliation against the realistic funding model (TDD, mutation-verified).

Phase 41 wired the realistic 8h funding-settlement model into the paper exchange.
This suite closes the loop on the *ledger* side: ``EventLedger.reconcile_funding``
binds the funding the exchange recorded into the ledger against the per-settlement
legs produced by ``src.evaluation.funding_model`` via ``reconcile_funding_legs``.

A mismatch (model net != ledger net) means the recorded fills drifted from the
settlement-accurate model, so the check is fail-closed: it reports ``in_sync=False``
rather than laundering a discrepancy into "balanced". No network, no signed calls.
"""
from __future__ import annotations

import pytest

from src.evaluation.funding_model import (
    EIGHT_HOURS_MS,
    FundingLeg,
    reconcile_funding_legs,
    settlement_funding_leg,
)
from src.ledger.sqlite import EventLedger


def _leg(side, quantity, mark, rate, k):
    """Build a FundingLeg for the k-th 8h settlement boundary via the shared model."""
    paid, received = settlement_funding_leg(side, quantity, mark, rate)
    return FundingLeg(ts_ms=(k + 1) * EIGHT_HOURS_MS, rate=rate, mark=mark,
                      paid=paid, received=received)


def test_reconcile_funding_matches_model_legs_when_ledger_is_consistent(tmp_path):
    """Recorded fill funding equals the sum of per-settlement legs -> in_sync."""
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    # Two settlements for a long 1.0 @ mark 100, rate +/-0.0001.
    leg1 = _leg("BUY", 1.0, 100.0, 0.0001, 0)
    leg2 = _leg("BUY", 1.0, 100.0, -0.0001, 1)
    legs = [leg1, leg2]
    model_net = reconcile_funding_legs(legs)  # +0.01 then -0.01 -> 0.0
    assert model_net == pytest.approx(0.0)

    funding_total = 0.0
    for leg in legs:
        funding_total += leg.paid - leg.received
        ledger.append("FILL_OBSERVED", {
            "cycle_id": "c1", "client_order_id": f"o{leg.ts_ms}", "symbol": "BTCUSDT",
            "side": "BUY", "quantity": 1.0, "price": leg.mark,
            "fee": 0.0, "funding": leg.paid - leg.received,
        })
    result = ledger.reconcile_funding(legs)
    assert result["in_sync"] is True
    assert result["model_net"] == pytest.approx(model_net)
    assert result["ledger_net"] == pytest.approx(funding_total)
    assert result["legs"] == 2


def test_reconcile_funding_mismatch_is_failed_closed(tmp_path):
    """If the ledger's recorded funding disagrees with the model, in_sync=False."""
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    leg = _leg("BUY", 1.0, 100.0, 0.0001, 0)
    # Record a DIFFERENT funding than the model leg implies (e.g. double-charged).
    ledger.append("FILL_OBSERVED", {
        "cycle_id": "c1", "client_order_id": "o1", "symbol": "BTCUSDT",
        "side": "BUY", "quantity": 1.0, "price": 100.0, "fee": 0.0,
        "funding": (leg.paid - leg.received) * 2.0,
    })
    result = ledger.reconcile_funding([leg])
    assert result["in_sync"] is False
    assert result["model_net"] != pytest.approx(result["ledger_net"])


def test_reconcile_funding_empty_is_in_sync(tmp_path):
    """No legs and no recorded funding reconcile trivially (vacuous consistency)."""
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    result = ledger.reconcile_funding([])
    assert result["in_sync"] is True
    assert result["model_net"] == 0.0
    assert result["ledger_net"] == 0.0
