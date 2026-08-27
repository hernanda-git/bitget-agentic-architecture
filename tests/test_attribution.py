"""Strategy attribution: decompose measured per-strategy returns honestly.

RED first. ``src.evaluation.attribution`` does not exist yet, so every test below
must fail for the right reason (ImportError / AttributeError), then pass after GREEN.

Strategy attribution answers: *given a set of candidate strategy return series
(alreadymeasured, e.g. walk-forward out-of-sample), how is the aggregate result
decomposed across families, what is each family's honest contribution, and how
concentrated is the edge?* It is DESCRIPTIVE ONLY.

MEASUREMENT ONLY. The output always carries ``selection_blocked=True`` and never
emits a promotion / selection / winner flag, so it cannot change the deterministic
Phase 6 promotion gate (which stays NEGATIVE_NET_PNL / blocked). Attribution does
not select, rank-for-selection, or recommend allocation. It reports contribution
and dispersion so researchers can see whether any measured edge is broad or a single
artifact.
"""
import json
import math

import pytest

from src.evaluation.attribution import attribute_performance


# --- Existence / contract (fails before implementation) ---
def test_module_and_function_exist():
    result = attribute_performance({"A": [0.01, -0.02, 0.03], "B": [0.02, 0.01, -0.01]})
    assert isinstance(result, dict)
    for key in ("selection_blocked", "attribution_is_descriptive", "n_strategies",
                "evidenced_count", "strategies", "total_net", "blend", "cross_sectional"):
        assert key in result
    assert result["selection_blocked"] is True
    assert result["attribution_is_descriptive"] is True
    # No selection / winner / promotion leakage is ever present.
    for forbidden in ("winner", "promotion_allowed", "selection"):
        assert forbidden not in result


# --- Fail-closed preconditions ---
def test_requires_at_least_two_strategies():
    with pytest.raises(ValueError):
        attribute_performance({"A": [0.01, 0.02, 0.03]})


def test_empty_series_raises():
    with pytest.raises(ValueError):
        attribute_performance({"A": [], "B": [0.01, 0.02, 0.03]})


def test_non_finite_raises():
    with pytest.raises(ValueError):
        attribute_performance({"A": [1.0, math.nan], "B": [0.01, 0.02]})
    with pytest.raises(ValueError):
        attribute_performance({"A": [1.0, math.inf], "B": [0.01, 0.02]})


# --- Per-strategy arithmetic ---
def test_per_strategy_expectancy_and_ci_bounds():
    a = [0.1, 0.2, 0.3, -0.1]
    b = [-0.05, 0.0, 0.05, 0.1]
    result = attribute_performance({"A": a, "B": b})
    sa = result["strategies"]["A"]
    assert sa["n"] == 4
    assert sa["expectancy"] == pytest.approx(0.125)
    assert sa["net_total"] == pytest.approx(0.5)
    lo, hi = sa["bootstrap_ci"]
    assert lo is not None and hi is not None
    assert lo <= sa["expectancy"] <= hi
    assert lo < hi  # series has spread, so the interval is non-degenerate
    assert sa["sharpe"] is not None and math.isfinite(sa["sharpe"])


def test_not_evidenced_below_min_samples():
    # min_samples=5; A has only 2 observations -> NOT_EVIDENCED.
    result = attribute_performance(
        {"A": [0.1, 0.2], "B": [0.01] * 10},
        min_samples=5,
    )
    assert result["strategies"]["A"]["evidence_status"] == "NOT_EVIDENCED"
    assert result["strategies"]["B"]["evidence_status"] == "EVIDENCED"
    assert result["evidenced_count"] == 1


def test_share_of_net_sums_to_one_when_positive():
    # Two families with equal, large net; shares must each be 0.5 and sum to 1.
    a = [1.0] * 40
    b = [1.0] * 40
    result = attribute_performance({"A": a, "B": b})
    sa, sb = result["strategies"]["A"], result["strategies"]["B"]
    assert sa["share_of_net"] == pytest.approx(0.5)
    assert sb["share_of_net"] == pytest.approx(0.5)
    assert (sa["share_of_net"] + sb["share_of_net"]) == pytest.approx(1.0)


def test_zero_total_net_avoids_division_by_zero():
    # Net cancels to zero; share_of_net must be None rather than crash.
    a = [1.0] * 40
    b = [-1.0] * 40
    result = attribute_performance({"A": a, "B": b})
    assert result["total_net"] == pytest.approx(0.0)
    assert result["strategies"]["A"]["share_of_net"] is None
    assert result["strategies"]["B"]["share_of_net"] is None
    # Concentration still well-defined on absolute magnitudes.
    assert result["cross_sectional"]["top_abs_share"] == pytest.approx(0.5)


# --- Descriptive blend is clearly non-selection ---
def test_blend_is_descriptive_and_blocked():
    a = [0.1, -0.05, 0.2]
    b = [-0.1, 0.05, -0.02]
    result = attribute_performance({"A": a, "B": b})
    blend = result["blend"]
    assert blend["is_descriptive"] is True
    assert blend["selection_blocked"] is True
    assert blend["n"] == min(len(a), len(b)) == 3
    # Blend expectancy equals the equal-weight per-step mean.
    expected = (sum((a[i] + b[i]) / 2 for i in range(3))) / 3
    assert blend["expectancy"] == pytest.approx(expected)
    # Blend must never smuggle in a selection verdict.
    for forbidden in ("winner", "promotion_allowed", "selection"):
        assert forbidden not in blend


# --- Concentration / dispersion ---
def test_concentration_top_abs_share():
    # A dominates absolute contribution; cross-sectional top share must reflect it.
    a = [1.0] * 40       # abs total 40
    b = [-0.1] * 40      # abs total 4
    result = attribute_performance({"A": a, "B": b})
    cs = result["cross_sectional"]
    assert cs["top_abs_contributor"] == "A"
    assert cs["top_abs_share"] == pytest.approx(40.0 / 44.0)


# --- Determinism / reproducibility ---
def test_deterministic_ordering():
    inp = {"B": [0.1, -0.2, 0.3], "A": [0.2, 0.1, -0.05]}
    r1 = attribute_performance(inp)
    r2 = attribute_performance(inp)
    assert list(r1["strategies"].keys()) == list(r2["strategies"].keys())
    assert r1 == r2


def test_reproducible_ci_same_seed():
    a = [0.1, -0.2, 0.3, 0.05, -0.1, 0.2]
    r1 = attribute_performance({"A": a, "B": [-x for x in a]}, seed=7)
    r2 = attribute_performance({"A": a, "B": [-x for x in a]}, seed=7)
    assert r1["strategies"]["A"]["bootstrap_ci"] == r2["strategies"]["A"]["bootstrap_ci"]


# --- Real-shaped input from already-local public history (no network) ---
def test_real_shaped_local_history_does_not_select():
    try:
        d = json.load(open("data/history/BTCUSDT_1m.json"))
    except FileNotFoundError:
        pytest.skip("local history fixture not present")
    closes = [float(c[4]) for c in d["candles"]]

    def momentum_returns(lookback):
        out = []
        for i in range(lookback + 1, len(closes)):
            prev = (closes[i] - closes[i - lookback]) / closes[i - lookback]
            cur = (closes[i - 1] - closes[i - 1 - lookback]) / closes[i - 1 - lookback]
            out.append(math.copysign(1.0, prev) * (closes[i] - closes[i - 1]) / closes[i - 1])
        return out

    strat = {
        "momentum_lb3": momentum_returns(3),
        "momentum_lb8": momentum_returns(8),
    }
    result = attribute_performance(strat)
    assert result["n_strategies"] == 2
    assert result["selection_blocked"] is True
    assert result["evidenced_count"] == 2  # 2500 candles -> well-sampled families
    assert all(s["evidence_status"] == "EVIDENCED" for s in result["strategies"].values())
