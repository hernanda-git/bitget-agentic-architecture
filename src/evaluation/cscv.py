"""Combinatorial Symmetric Cross-Validation (CSCV) PBO robustness metric.

Measurement only. Complements Deflated Sharpe + Holm (``walk_forward_strength``)
by asking the overfitting question directly: does the train-best configuration
also generalize out-of-sample? CSCV (Bailey & Lopez de Prado, 2014) partitions
each strategy's per-block performance into S blocks, exhaustively (or sampled)
splits the S blocks into train/test halves, ranks strategies by train and by test
within each split, and reports:

  * ``pbo``: fraction of splits where the train-best strategy lands in the bottom
    half out-of-sample (relative rank > N/2). High PBO means overfit.
  * ``mean_r_squared``: mean Pearson R^2 between train ranks and test ranks across
    splits. High means rank-stable / generalizes.

Output always carries ``selection_blocked=True`` and never emits a
promotion / selection / winner flag, so it cannot change the deterministic Phase 6
promotion gate (which stays NEGATIVE_NET_PNL / blocked).
"""
from __future__ import annotations

import math
import random
from itertools import combinations

_MIN_BLOCKS = 4


def _rank_desc(values):
    """1-based ranks (1 = highest value) with average-rank tie handling."""
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson_r(x, y):
    """Signed Pearson correlation; 0.0 when either side is degenerate."""
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0.0 or syy == 0.0:
        return 0.0
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / math.sqrt(sxx * syy)


def cscv_pbo(performance_matrix, *, seed: int = 0, max_combinations: int | None = None) -> dict:
    """Probability of Backtest Overfitting via Combinatorial Symmetric Cross-Validation.

    ``performance_matrix`` is an iterable of N strategy rows, each a sequence of S
    finite per-block performance numbers (e.g. per-block Sharpe ratios). S must be
    even and >= 4, N >= 2. When C(S, S/2) exceeds ``max_combinations`` the partitions
    are sampled deterministically with ``seed``.
    """
    matrix = [[float(v) for v in row] for row in performance_matrix]
    if not matrix:
        raise ValueError("cscv_pbo requires at least one strategy row")
    n_strategies = len(matrix)
    n_blocks = len(matrix[0])
    for row in matrix:
        if len(row) != n_blocks:
            raise ValueError("cscv_pbo requires every strategy row to have the same number of blocks")
    if n_strategies < 2:
        raise ValueError("cscv_pbo requires at least 2 strategies")
    if n_blocks < _MIN_BLOCKS:
        raise ValueError("cscv_pbo requires at least %d blocks" % _MIN_BLOCKS)
    if n_blocks % 2 != 0:
        raise ValueError("cscv_pbo requires an even number of blocks")
    for row in matrix:
        for v in row:
            if not math.isfinite(v):
                raise ValueError("cscv_pbo requires finite performance values")

    S = n_blocks
    half = S // 2
    all_splits = list(combinations(range(S), half))
    if max_combinations is not None and max_combinations >= 1 and len(all_splits) > max_combinations:
        rng = random.Random(seed)
        chosen = rng.sample(all_splits, max_combinations)
    else:
        chosen = all_splits

    pbo_count = 0
    r_sum = 0.0
    r2_sum = 0.0
    for train_blocks in chosen:
        test_blocks = [b for b in range(S) if b not in train_blocks]
        train_means = [sum(row[b] for b in train_blocks) / half for row in matrix]
        test_means = [sum(row[b] for b in test_blocks) / half for row in matrix]
        train_ranks = _rank_desc(train_means)
        test_ranks = _rank_desc(test_means)
        # train-best: lowest train rank (rank 1 = best performance); ties broken by
        # lowest index. _rank_desc assigns 1 to the highest value, so the best is min.
        best_idx = min(range(n_strategies), key=lambda i: (train_ranks[i], i))
        best_test = test_means[best_idx]
        n_strictly_greater = sum(1 for v in test_means if v > best_test)
        relative_rank = 1 + n_strictly_greater
        if relative_rank > n_strategies / 2.0:
            pbo_count += 1
        r = _pearson_r(train_ranks, test_ranks)
        r_sum += r
        r2_sum += r * r

    K = len(chosen)
    pbo = pbo_count / K if K else 0.0
    mean_r = r_sum / K if K else 0.0
    mean_r2 = r2_sum / K if K else 0.0
    if pbo >= 0.5:
        risk = "HIGH"
    elif pbo >= 0.4:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    return {
        "n_strategies": n_strategies,
        "n_blocks": n_blocks,
        "combinations": K,
        "pbo": pbo,
        "mean_r": mean_r,
        "mean_r_squared": mean_r2,
        "overfit_risk": risk,
        "selection_blocked": True,
    }


def _sharpe(returns):
    n = len(returns)
    if n < 2:
        return 0.0
    m = sum(returns) / n
    var = sum((x - m) ** 2 for x in returns) / (n - 1)
    if var == 0.0:
        return 0.0
    return m / math.sqrt(var)


def performance_matrix_from_returns(returns_by_strategy, *, block_size: int, metric: str = "sharpe") -> list:
    """Build an S-block performance matrix from per-strategy return series.

    Each series is chopped into contiguous blocks of ``block_size`` returns; the
    chosen ``metric`` (``"sharpe"`` or ``"mean"``) is computed per block. Used to
    feed ``cscv_pbo`` from real replay return streams. Fail-closed: every series
    must be non-empty and its length must be exactly divisible by ``block_size``.
    """
    if block_size < 1:
        raise ValueError("block_size must be >= 1")
    if metric not in ("sharpe", "mean"):
        raise ValueError("unsupported metric: %s" % metric)
    matrix = []
    for returns in returns_by_strategy:
        series = [float(r) for r in returns]
        if not series:
            raise ValueError("each return series must be non-empty")
        if len(series) % block_size != 0:
            raise ValueError("return series length must be divisible by block_size")
        n_blocks = len(series) // block_size
        row = []
        for b in range(n_blocks):
            seg = series[b * block_size:(b + 1) * block_size]
            if metric == "sharpe":
                row.append(_sharpe(seg))
            else:
                row.append(sum(seg) / len(seg))
        matrix.append(row)
    return matrix
