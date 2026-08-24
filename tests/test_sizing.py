import pytest

from src.policy.sizing import SizingError, size_for_risk


def test_sizes_from_stop_distance_and_reports_effective_risk():
    result = size_for_risk(side="BUY", entry=100, stop_loss=95, requested_risk_usd=10,
                           min_notional_usd=5, max_notional_usd=1000, quantity_step=0.1)
    assert result.quantity == 2
    assert result.notional_usd == 200
    assert result.effective_risk_usd == 10
    assert result.raised_to_minimum is False


def test_max_notional_caps_realized_risk():
    result = size_for_risk(side="SELL", entry=100, stop_loss=110, requested_risk_usd=100,
                           min_notional_usd=5, max_notional_usd=50, quantity_step=0.1)
    assert result.notional_usd == 50
    assert result.effective_risk_usd == 5
    assert result.capped_by_max is True


@pytest.mark.parametrize("side,stop", [("BUY", 100), ("SELL", 100)])
def test_stop_geometry_is_required(side, stop):
    with pytest.raises(SizingError):
        size_for_risk(side=side, entry=100, stop_loss=stop, requested_risk_usd=1,
                      min_notional_usd=5, max_notional_usd=100, quantity_step=1)


def test_minimum_notional_is_enforced():
    result = size_for_risk(side="BUY", entry=100, stop_loss=99, requested_risk_usd=0.1,
                           min_notional_usd=50, max_notional_usd=1000, quantity_step=0.1)
    assert result.notional_usd >= 50
    assert result.raised_to_minimum is True
