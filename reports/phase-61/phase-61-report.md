# Phase 61 — Regime-Conditioned Attribution Pipeline Verified

**Status:** research/measurement infrastructure; no profitability claim.
**Safety:** offline public-history replay only; shadow mode; no signed calls, no orders, no live execution.

## Why this phase

The Phase 55 evaluation family identified the next research gate as **attribution of losses into gross signal vs costs/exits/adverse selection**. The existing `attribute_performance` function decomposes per-strategy returns by *family* but never answers the honest-edge question: *is the edge concentrated in one market regime?*

This phase closes the loop: bridge real `classify_regime` labels into per-strategy walk-forward attribution so regime-conditioned attribution is live in the deterministic pipeline. The bridge is descriptive only — it never selects, ranks, or promotes a strategy.

## Changes

- `src/evaluation/regime_attribution.py` — pre-existing module bridging `classify_regime` into `attribute_performance_by_regime` via `attribution_by_regime_windows()`, `window_regime_labels()`, `_window_bounds()`.
- `tests/test_regime_attribution.py` — 8 tests covering regime decomposition, net/concentration, selection always blocked, alignment rejection, non-finite rejection, single-strategy rejection, degraded regime label handling, finite bootstrap CI.
- `tests/test_regime_attribution_bridge.py` — 6 tests covering bridge alignment with walk-forward geometry, never-promotes/overclaims, window-bounds consistency, mid-snapshot regime label, fail-closed on empty input, fail-closed on geometry mismatch.

## RED / GREEN / mutation evidence

### RED verified
- `test_attribution_by_regime_rejects_mismatched_alignment`: short regime label list raises `ValueError`.
- `test_attribution_by_regime_rejects_non_finite`: NaN/infinite returns raise `ValueError`.
- `test_attribution_by_regime_rejects_single_strategy`: single-strategy input raises `ValueError`.
- `test_bridge_fails_closed_on_empty_input`: empty snapshots raises `ValueError`.
- `test_bridge_fails_closed_on_geometry_mismatch`: mocked window-count mismatch raises `ValueError`.

### GREEN verified
- All 45 tests across the attribution + regime attribution cluster pass (`test_attribution.py`, `test_regime_attribution.py`, `test_regime_attribution_bridge.py`, `test_strategy_attribution.py`, `test_hypothesis_default_registry.py`, `test_hypothesis_outcomes.py`).
- Full test battery: **733 passed / 4 skipped / 0 failed**.

### Mutation verification
- **`test_bridge_fails_closed_on_geometry_mismatch`**: patches `mod.run_strategy_attribution` to drop one strategy's last window, confirming the bridge raises `ValueError` when window counts diverge. Mutation was reverted after confirming RED→GREEN.
- **`test_attribution_by_regime_rejects_mismatched_alignment`**: feeds a 3-element regime label list against 6-step return streams; confirms `ValueError`.
- **`test_attribution_by_regime_rejects_non_finite`**: feeds NaN/infinite returns; confirms `ValueError`.

## Honest measurement

| Component | Tests | Status |
|---|---:|---|
| `attribute_performance_by_regime` | 8 | PASS |
| `attribution_by_regime_windows` bridge | 6 | PASS |
| `attribute_performance` (family) | 13 | PASS |
| `strategy_attribution` | 7 | PASS |
| `hypothesis` registry/outcomes | 11 | PASS |
| **Full suite** | **733** | **PASS** |

The regime bridge produces aligned window labels from `classify_regime` and feeds them into the same walk-forward windows used by `run_strategy_attribution`. Every regime label is one actually computed by `classify_regime` at the window's midpoint snapshot (verified by `test_window_regime_label_uses_mid_snapshot`).

## Honest status

This phase verified the regime-conditioned attribution infrastructure end-to-end. The deterministic baseline remains **negative** and **promotion remains blocked**. No profitability is claimed. The regime bridge is a measurement/descriptive tool that helps researchers understand *where* (which regime) measured returns concentrate — it does not select, rank, or promote.

## Next alpha gate

With the regime-conditioned attribution pipeline verified, the next phase can now run the purged label/holding-period evaluation on the fresh public-history corpus. The `make_holding_period_labels` function already exists in `src/features/technical.py` and is tested. The next bounded phase should:
1. Use `make_holding_period_labels` to create forward-return labels for configurable holding periods (not just 1-bar).
2. Evaluate one structurally distinct hypothesis (funding/basis or flow/price divergence) with purged chronological validation on the fresh corpus.
3. Run the cost sensitivity sweep to determine the break-even cost multiplier for any observed edge.

No profitability claim is allowed. The deterministic promotion gate (`NEGATIVE_NET_PNL`) remains the only thing that may unblock promotion.
