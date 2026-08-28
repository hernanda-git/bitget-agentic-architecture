# Phase 30 — Bridge regime classification into strategy attribution (TDD + mutation-verified)

**Date:** autonomous cron run (Asia/Jakarta timezone)
**Mode:** offline, no network, no credentials, no orders, no signed calls.
**Scope:** close the gap that phase-29 left open — nothing in the pipeline actually
fed real `classify_regime` labels into `attribute_performance_by_regime`.

## What was added

`src/evaluation/regime_attribution.py` bridges the real regime-classification path
into the per-strategy attribution:

* `_window_bounds(config, n)` — pure walk-forward window geometry
  `(test_start, test_end, mid_index)`, mirroring `run_walk_forward` exactly.
* `window_regime_labels(snapshots, config)` — one regime label per window, from
  the window's **midpoint** snapshot (the representative bar of that window).
* `attribution_by_regime_windows(snapshots, config)` — calls
  `run_strategy_attribution` (which evaluates every canonical strategy alone
  across the SAME walk-forward windows, so its per-strategy `windows_net_pnl`
  lists are aligned by window index), classifies each window, and hands the
  aligned streams to `attribute_performance_by_regime`.

This makes the regime edge-concentration report driven by the *real* regime
classifier on the same data the baseline already evaluates — not a hand-fed toy
label series.

## TDD cycle

RED first: `tests/test_regime_attribution_bridge.py` written before the module
existed; collection failed with `ModuleNotFoundError: No module named
'src.evaluation.regime_attribution'` (feature missing). Confirmed RED.

GREEN: implemented the three functions minimally. Alignment is enforced
fail-closed: if any strategy's window count diverges from the regime label count,
the bridge raises `ValueError` rather than emitting a misaligned report.

## Mutation verification (assertions are not decorative)

`test_window_bounds_consistency_with_run_walk_forward` asserts `_window_bounds`
equals the geometry `run_walk_forward` actually produces. A deliberate mutation —
dropping the `config.embargo` term from the window advance — made the test FAIL
(`(59, 68, 63) != (60, 69, 64)`, one extra window), proving the guard catches a
geometry divergence. Reverted: 6/6 bridge tests pass.

`test_bridge_fails_closed_on_geometry_mismatch` monkeypatches
`run_strategy_attribution` to drop one strategy's last window and asserts the
bridge refuses with `ValueError`.

## Honest findings

* The bridge is descriptive only: `selection_blocked` stays `True`, no
  `winner`/`promoted`/`best`/`selected`/`promotion_allowed` keys are emitted, and
  `find_overclaims` returns `[]`.
* `source` is explicitly `"walk_forward_window_returns"` so the dashboard can
  label the provenance of the regime decomposition.
* Synthetic oscillator series (positive prices, multiple regimes) yields a clean
  multi-window attribution with no crashes.

## Verification

* 6 new unit tests pass (`tests/test_regime_attribution_bridge.py`).
* `compileall` clean.
* No network, no signed calls, no orders, no credentials touched.

## Limitations (explicit, not hidden)

* Window granularity is the walk-forward window, not the individual candle. This
  matches `run_strategy_attribution`'s resolution (per-window net PnL per strategy)
  and keeps alignment trivial; candle-level regime conditioning would require a
  per-candle replay path not yet present in the baseline.
* `min_samples=30` bootstrap default means small regimes get appropriately wide CIs.
* Descriptive only: does not, and cannot, unblock Phase 6 promotion (which stays
  blocked by the deterministic NEGATIVE_NET_PNL baseline).
