"""Bridge regime classification into strategy attribution (TDD: RED first).

``src.evaluation.attribution.attribute_performance_by_regime`` already slices
per-strategy return streams by an externally supplied regime label series, but
nothing in the pipeline *produces* those labels from the real
``classify_regime`` path. ``run_strategy_attribution`` evaluates every canonical
strategy alone across the SAME walk-forward windows, so its per-strategy
``windows_net_pnl`` lists are aligned by window index. This module closes the
loop: classify each window's regime from a real snapshot and feed the aligned
streams into the regime attribution.

The bridge is descriptive only: ``selection_blocked`` stays ``True``, no winner
/ promoted / best keys are ever emitted, and it fails closed if the window
geometry and the attribution window count disagree.
"""
from __future__ import annotations

import pytest

from src.evaluation.baseline import BaselineConfig, run_strategy_attribution, run_walk_forward
from src.evaluation.regime_attribution import (
    attribution_by_regime_windows,
    window_regime_labels,
    _window_bounds,
)
from src.evaluation.report_honesty import find_overclaims
from src.market.models import Candle, MarketSnapshot
from src.strategies.regime import classify_regime
import math


def _series(count: int = 80):
    """Deterministic, always-positive snapshot series yielding several
    walk-forward windows (train_fraction=0.6, embargo=1, test_window=10)."""
    start = 1_700_000_000_000
    out = []
    for i in range(count):
        closes = [100 + 8 * math.sin((i + j) / 4.0) + j * 0.3 for j in range(12)]
        candles = tuple(
            Candle("1m", c - 0.5, c + 1, c - 1, c, 10, start + j * 60_000)
            for j, c in enumerate(closes)
        )
        ts = start + (len(closes) - 1) * 60_000
        out.append(
            MarketSnapshot(
                "BTCUSDT", closes[-1], closes[-1] - 0.01, closes[-1] + 0.01,
                0.0002, 100, ts, ts, candles=candles,
            ).with_hash()
        )
    return tuple(out)


def test_bridge_produces_regime_attribution_aligned_to_windows():
    """The bridge returns a regime attribution whose window count matches the
    walk-forward windows used by ``run_strategy_attribution``."""
    snapshots = _series(80)
    config = BaselineConfig()
    report = attribution_by_regime_windows(snapshots, config)

    attr = run_strategy_attribution(snapshots, config)
    n_attr_windows = len(attr["trend_continuation"]["windows_net_pnl"])

    # The bridge must observe exactly the same number of windows the
    # attribution produced, and every regime key must be one actually seen.
    assert report["n_windows"] == n_attr_windows
    assert report["n_windows"] > 0
    assert set(report["regimes"].keys()) <= set(report["regime_labels_observed"])
    # Source of the returns is explicit and honest.
    assert report["source"] == "walk_forward_window_returns"


def test_bridge_never_promotes_or_overclaims():
    """Descriptive bridge: never flips the promotion gate, never emits a winner,
    and passes the generic overclaim scanner."""
    snapshots = _series(80)
    report = attribution_by_regime_windows(snapshots)

    # No promotion / winner keys anywhere in the report.
    assert report["selection_blocked"] is True
    assert report.get("bridge_selection_blocked") is True
    banned = ("winner", "promoted", "best", "selected", "promotion_allowed")
    assert not any(k in report for k in banned)
    for block in (report["regimes"], report.get("strategies", {})):
        for sub in (block.values() if isinstance(block, dict) else []):
            if isinstance(sub, dict):
                assert not any(k in sub for k in banned)
    # The generic honesty scanner must find nothing.
    assert find_overclaims(report) == []


def test_window_bounds_consistency_with_run_walk_forward():
    """``_window_bounds`` must match the geometry ``run_walk_forward`` actually
    uses, so regime labels stay aligned with attribution windows. This is the
    mutation-checked consistency anchor: if either side changes its windowing
    math, this test fails."""
    snapshots = _series(80)
    config = BaselineConfig()
    wf = run_walk_forward(snapshots, config)
    bounds = _window_bounds(config, len(snapshots))
    expected = [
        (row["test_start"], row["test_end"], (row["test_start"] + row["test_end"]) // 2)
        for row in wf
    ]
    assert bounds == expected
    assert len(bounds) > 0


def test_window_regime_label_uses_mid_snapshot():
    """Each window's label is the regime of that window's midpoint snapshot."""
    snapshots = _series(80)
    config = BaselineConfig()
    labels = window_regime_labels(snapshots, config)
    bounds = _window_bounds(config, len(snapshots))
    assert len(labels) == len(bounds)
    for (_, _, mid), label in zip(bounds, labels):
        assert label == classify_regime(snapshots[mid]).value


def test_bridge_fails_closed_on_empty_input():
    """No snapshots => no windows => fail closed (never a silent empty report)."""
    with pytest.raises(ValueError):
        attribution_by_regime_windows([], BaselineConfig())


def test_bridge_fails_closed_on_geometry_mismatch():
    """If the attribution window count ever diverges from the regime label
    count, the bridge must refuse rather than produce a misaligned report."""
    snapshots = _series(80)
    config = BaselineConfig()

    real = run_strategy_attribution(snapshots, config)

    def _fake_attr(*a, **k):
        fake = dict(real)
        # Drop one strategy's last window to break alignment.
        name = fake["strategies_evaluated"][0]
        fake[name] = dict(fake[name])
        fake[name]["windows_net_pnl"] = fake[name]["windows_net_pnl"][:-1]
        return fake

    import src.evaluation.regime_attribution as mod
    original = mod.run_strategy_attribution
    mod.run_strategy_attribution = _fake_attr
    try:
        with pytest.raises(ValueError):
            attribution_by_regime_windows(snapshots, config)
    finally:
        mod.run_strategy_attribution = original
