"""CSCV probability-of-backtest-overfitting (PBO) robustness metric.

RED first. ``src.evaluation.cscv`` does not exist yet, so every test below must
fail for the right reason (ImportError / AttributeError), then pass after GREEN.

CSCV (Bailey & Lopez de Prado, 2014) splits each strategy's per-block performance
into S blocks, then exhaustively (or sampled) partitions the S blocks into
train/test halves. For each partition it ranks strategies by train performance and
by test performance, measures the rank correlation, and counts how often the
train-best strategy falls in the bottom half out-of-sample. ``pbo`` is that
fraction; ``mean_r_squared`` is the mean Pearson R^2 between train and test ranks.

This directly strengthens walk-forward robustness evidence and complements the
existing Deflated Sharpe + Holm correction (``walk_forward_strength``). It asks
the overfitting question the other two metrics do not: does the train-best
configuration also generalize?

MEASUREMENT ONLY. Output always carries ``selection_blocked=True`` and never emits
a promotion / selection / winner flag, so it cannot change the deterministic Phase
6 promotion gate (which stays NEGATIVE_NET_PNL / blocked).
"""
import json
import math
import pathlib

import pytest

from src.evaluation.cscv import cscv_pbo, performance_matrix_from_returns


def _matrix(*rows):
    return [list(r) for r in rows]


# --- Existence / shape contract (fails before implementation) ---
def test_cscv_pbo_module_and_function_exist():
    result = cscv_pbo(_matrix([0.0, 1.0, 2.0, 3.0], [3.0, 2.0, 1.0, 0.0]))
    assert isinstance(result, dict)
    for key in ("n_strategies", "n_blocks", "combinations", "pbo",
                "mean_r", "mean_r_squared", "overfit_risk", "selection_blocked"):
        assert key in result


# --- Robust edge: a block-invariant strategy keeps its train rank out-of-sample ---
def test_robust_constant_per_strategy_yields_zero_pbo():
    # Each strategy i has a constant (block-invariant) performance. The train rank
    # equals the test rank for every partition, so the train-best stays best
    # out-of-sample -> PBO = 0 and perfect rank correlation.
    N = 6
    matrix = [[float(i)] * N for i in range(N)]  # row i is constant i, N blocks
    result = cscv_pbo(matrix)
    assert result["n_strategies"] == N
    assert result["n_blocks"] == N
    assert result["pbo"] == 0.0
    assert result["mean_r_squared"] == pytest.approx(1.0, abs=1e-9)
    assert result["mean_r"] > 0.9  # ranks perfectly positively correlated
    assert result["overfit_risk"] == "LOW"


# --- Overfit: each strategy "fits" exactly one disjoint fold and is worst elsewhere ---
def test_overfit_fold_specialist_yields_high_pbo():
    # Classic overfit. Strategy i is +1 only in block i and 0 elsewhere. In any
    # train/test split the train-best is the strategy whose winning block landed in
    # train, whose winning block is therefore NOT in test -> it is strictly worse
    # out-of-sample than every strategy whose block is in test. Train and test ranks
    # are anti-correlated on average. This must read as a high PBO / HIGH risk.
    S = 6
    N = 6
    matrix = [[1.0 if b == i else 0.0 for b in range(S)] for i in range(N)]
    result = cscv_pbo(matrix)
    assert result["pbo"] > 0.5, result
    assert result["overfit_risk"] == "HIGH"
    # Signed rank correlation is negative (train-best rank is anti-correlated with
    # test rank); the squared value stays non-negative.
    assert result["mean_r"] < 0.0
    assert 0.0 <= result["mean_r_squared"] <= 1.0


# --- Invariant: PBO and R^2 stay in their valid ranges for arbitrary matrices ---
def test_pbo_and_r_squared_in_valid_ranges():
    rng_rows = [
        [0.1, -0.4, 0.7, 0.2, -0.1, 0.3],
        [0.5, 0.5, -0.2, 0.0, 0.9, -0.3],
        [-0.2, 0.1, 0.2, -0.5, 0.4, 0.6],
    ]
    result = cscv_pbo(rng_rows)
    assert 0.0 <= result["pbo"] <= 1.0
    assert -1.0 <= result["mean_r_squared"] <= 1.0


# --- Combinatorial accounting: uncapped S=4 exhausts C(4,2)=6 partitions ---
def test_pbo_counts_all_combinations_when_uncapped():
    matrix = [[0.0, 1.0, 2.0, 3.0], [3.0, 2.0, 1.0, 0.0], [1.0, 1.0, 1.0, 1.0]]
    result = cscv_pbo(matrix)
    assert result["combinations"] == 6


# --- Sampling cap must bound the number of evaluated partitions ---
def test_pbo_caps_combinations_when_requested():
    S = 8
    matrix = [[1.0 if b == i else -1.0 for b in range(S)] for i in range(S)]
    result = cscv_pbo(matrix, max_combinations=20)
    assert 1 <= result["combinations"] <= 20
    assert 0.0 <= result["pbo"] <= 1.0


# --- Fail-closed preconditions ---
def test_too_few_blocks_raises():
    with pytest.raises(ValueError):
        cscv_pbo([[0.0, 1.0], [1.0, 0.0]])  # S=2 < 4


def test_odd_blocks_raises():
    with pytest.raises(ValueError):
        cscv_pbo([[0.0, 1.0, 2.0], [1.0, 0.0, 3.0]])  # S=3 odd


def test_single_strategy_raises():
    with pytest.raises(ValueError):
        cscv_pbo([[0.0, 1.0, 2.0, 3.0]])


def test_non_finite_value_raises():
    with pytest.raises(ValueError):
        cscv_pbo([[0.0, float("nan"), 2.0, 3.0], [1.0, 0.0, 3.0, 2.0]])


def test_ragged_rows_raise():
    with pytest.raises(ValueError):
        cscv_pbo([[0.0, 1.0, 2.0, 3.0], [1.0, 0.0, 3.0]])


# --- Honesty: the metric never unblocks selection ---
def test_selection_blocked_always_true():
    result = cscv_pbo([[0.0, 1.0, 2.0, 3.0], [3.0, 2.0, 1.0, 0.0]])
    assert result["selection_blocked"] is True


# --- Helper: build a performance matrix from per-strategy return series ---
def test_performance_matrix_from_returns_blocks_and_metric():
    # Two strategies, 12 returns each, block_size 3 -> 4 blocks.
    s0 = [0.01, -0.02, 0.03, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    s1 = [0.0] * 12
    matrix = performance_matrix_from_returns([s0, s1], block_size=3, metric="sharpe")
    assert len(matrix) == 2
    assert all(len(row) == 4 for row in matrix)
    # First block of s0 is [0.01,-0.02,0.03]: mean > 0, var > 0 -> finite sharpe.
    assert math.isfinite(matrix[0][0])


def test_performance_matrix_rejects_undivisible_length():
    with pytest.raises(ValueError):
        performance_matrix_from_returns([[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]], block_size=2)


# --- Integration: run the metric over real local history (no network) ---
def test_cscv_on_real_history_is_well_formed():
    path = pathlib.Path("data/history/BTCUSDT_1m.json")
    if not path.exists():
        pytest.skip("local history not present (no network acquisition in this phase)")
    data = json.loads(path.read_text())
    candles = data["candles"]
    closes = [float(c[4]) for c in candles]
    # Build N strategy return series from simple momentum signals with varied
    # lookbacks so the matrix carries real-shaped cross-strategy variation.
    lookbacks = (3, 5, 8, 13, 21, 34)
    returns_by_strategy = []
    for look in lookbacks:
        rets = [closes[i] / closes[i - look] - 1.0 for i in range(look, len(closes))]
        returns_by_strategy.append(rets)
    minlen = min(len(r) for r in returns_by_strategy)
    trimmed = (minlen // 6) * 6  # make length divisible by 6 blocks
    returns_by_strategy = [r[-trimmed:] for r in returns_by_strategy]
    block_size = trimmed // 6
    matrix = performance_matrix_from_returns(returns_by_strategy, block_size=block_size, metric="sharpe")
    result = cscv_pbo(matrix)
    assert result["n_strategies"] == len(lookbacks)
    assert result["n_blocks"] == 6
    assert 0.0 <= result["pbo"] <= 1.0
    assert -1.0 <= result["mean_r_squared"] <= 1.0
    assert result["selection_blocked"] is True
