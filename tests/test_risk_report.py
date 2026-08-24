from src.policy.risk_report import EffectiveRiskReport, build_risk_report
from src.policy.sizing import size_for_risk


def test_report_uses_actual_venue_sized_risk_not_configured_risk():
    sizing = size_for_risk(side="BUY", entry=100, stop_loss=99, requested_risk_usd=0.5,
                           min_notional_usd=100, max_notional_usd=1_000, quantity_step=1)
    report = build_risk_report(sizing=sizing, equity_usd=1_000, daily_loss_cap_usd=20,
                              entry=100, stop_loss=99, margin_used_usd=50)
    assert isinstance(report, EffectiveRiskReport)
    assert report.requested_risk_usd == 0.5
    assert report.actual_quantity == 1
    assert report.actual_notional_usd == 100
    assert report.actual_stop_distance_usd == 1
    assert report.realized_risk_usd == 1
    assert report.risk_percent_equity == 0.1
    assert report.minimum_notional_distortion is True
    assert report.risk_vs_daily_cap == 0.05
    assert report.implied_leverage == 2


def test_report_marks_capped_risk_as_actual_and_not_configured():
    sizing = size_for_risk(side="SELL", entry=100, stop_loss=110, requested_risk_usd=100,
                           min_notional_usd=5, max_notional_usd=50, quantity_step=0.1)
    report = build_risk_report(sizing=sizing, equity_usd=1_000, daily_loss_cap_usd=20,
                              entry=100, stop_loss=110, margin_used_usd=10)
    assert report.realized_risk_usd == 5
    assert report.risk_percent_equity == 0.5
    assert report.minimum_notional_distortion is False
