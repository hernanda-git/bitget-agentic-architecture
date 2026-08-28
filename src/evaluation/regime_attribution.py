"""Bridge regime classification into strategy attribution (offline, fail-closed).

``run_strategy_attribution`` already evaluates every canonical strategy alone
across the SAME walk-forward windows, so its per-strategy ``windows_net_pnl``
lists are aligned by window index. ``attribute_performance_by_regime`` slices
those aligned per-strategy return streams by a regime label per step, but the
pipeline never produced those labels from the real ``classify_regime`` path.

This module closes the loop: classify each walk-forward window's regime from a
real snapshot and hand the aligned streams to the regime attribution.

The bridge is descriptive only. It never selects or promotes a strategy
(``selection_blocked`` stays ``True``), never emits ``winner``/``promoted``/
``best`` keys, and fails closed if the window geometry and the attribution
window count ever disagree. No network, no credentials, no signed calls.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from src.evaluation.attribution import attribute_performance_by_regime
from src.evaluation.baseline import BaselineConfig, run_strategy_attribution
from src.strategies.regime import Regime, classify_regime


def _window_bounds(config: BaselineConfig, n: int) -> List[Tuple[int, int, int]]:
    """Pure walk-forward window geometry: ``(test_start, test_end, mid_index)``.

    Mirrors ``run_walk_forward`` in ``baseline.py`` exactly so the per-window
    regime labels stay aligned with ``run_strategy_attribution`` windows. If the
    two ever diverge, ``test_window_bounds_consistency_with_run_walk_forward``
    fails, surfacing the misalignment instead of silently mislabeling regimes.
    """
    if not 0 < config.train_fraction < 1 or config.embargo < 0 or config.test_window < 1:
        raise ValueError(
            "walk-forward parameters must have 0 < train_fraction < 1, "
            "embargo >= 0, and test_window >= 1"
        )
    cut = max(1, int(n * config.train_fraction))
    window = config.test_window
    bounds: List[Tuple[int, int, int]] = []
    test_start = cut + config.embargo
    while test_start + window <= n:
        test_end = test_start + window - 1
        mid = (test_start + test_end) // 2
        bounds.append((test_start, test_end, mid))
        test_start = test_end + 1 + config.embargo
    if not bounds:
        raise ValueError("walk-forward requires at least one complete test window")
    return bounds


def window_regime_labels(
    snapshots,
    config: BaselineConfig,
    classify: Callable = classify_regime,
) -> List[str]:
    """One regime label per walk-forward window, from the window's midpoint snapshot."""
    snapshots = tuple(snapshots)
    bounds = _window_bounds(config, len(snapshots))
    return [classify(snapshots[mid]).value for _start, _end, mid in bounds]


def attribution_by_regime_windows(
    snapshots,
    config: BaselineConfig = BaselineConfig(),
    classify: Callable = classify_regime,
) -> dict:
    """Bridge real regime classification into per-strategy attribution.

    Fail-closed: requires at least one window, and the per-strategy window
    counts must match the regime label count. Descriptive only: ``selection_blocked``
    stays ``True`` and no winner/promoted/best keys are emitted.
    """
    snapshots = tuple(snapshots)
    attr = run_strategy_attribution(snapshots, config)
    names = attr["strategies_evaluated"]
    if not names:
        raise ValueError("no strategies evaluated")

    strategy_returns: Dict[str, List[float]] = {
        name: list(attr[name]["windows_net_pnl"]) for name in names
    }
    labels = window_regime_labels(snapshots, config, classify)
    n_windows = len(labels)
    if n_windows == 0:
        raise ValueError("no walk-forward windows produced")

    for name, series in strategy_returns.items():
        if len(series) != n_windows:
            raise ValueError(
                f"strategy {name} window count {len(series)} != "
                f"regime label count {n_windows}"
            )

    report = attribute_performance_by_regime(strategy_returns, labels)
    report["source"] = "walk_forward_window_returns"
    report["n_windows"] = n_windows
    report["regime_labels_observed"] = sorted(set(labels))
    report["bridge_selection_blocked"] = report.get("selection_blocked", True)
    return report
