import pytest

from src.health.variation import assess_runtime_health, assess_variation


def test_identical_samples_are_reported_as_flatline():
    result = assess_variation(["HOLD", "HOLD", "HOLD"])

    assert result.status == "FLATLINE"
    assert result.samples == 3
    assert result.distinct_samples == 1


def test_changing_samples_are_reported_as_healthy():
    result = assess_variation(["HOLD", "ENTER", "MANAGE"])

    assert result.status == "HEALTHY"
    assert result.samples == 3
    assert result.distinct_samples == 3


def test_short_sample_windows_are_reported_as_insufficient():
    result = assess_variation(["HOLD", "ENTER"])

    assert result.status == "INSUFFICIENT_DATA"
    assert result.samples == 2


def test_runtime_health_reports_each_metric_and_degrades_on_flatline():
    result = assess_runtime_health(
        {"market_data": [100, 100, 100], "decisions": ["HOLD", "ENTER", "HOLD"]}
    )

    assert result["status"] == "DEGRADED"
    assert result["metrics"]["market_data"]["status"] == "FLATLINE"
    assert result["metrics"]["decisions"]["status"] == "HEALTHY"


def test_variation_requires_a_positive_sample_threshold():
    with pytest.raises(ValueError, match="minimum_samples"):
        assess_variation([1, 2], minimum_samples=0)
