"""Multi-symbol honest aggregation for the deterministic baseline (TDD: RED first).

The cron mandate calls for (a) acquiring more public historical data and
(b) strengthening walk-forward evaluation. As the stored evidence base grows
(more symbols, deeper windows), a single honest report must aggregate every
per-symbol result WITHOUT laundering the blocked baseline into a go-live claim.

This module aggregates per-symbol deterministic-baseline results into one
fail-closed report:

* ``selection_blocked`` is always carried through (Phase 6 remains blocked).
* ``aggregate_promotion_allowed`` is only ever True when selection is NOT
  blocked AND every symbol is positive AND every symbol is adequately sampled.
  With the repo's blocked baseline this is always False.
* the aggregate is self-validated by ``assert_truthful`` (recursive, per
  Phase 18), so a nested overclaim inside ANY per-symbol result is refused.

All tests are network-free: they feed synthetic per-symbol dicts into the
aggregator. No credentials, no signed calls, no orders.
"""
import pytest

from src.evaluation.multisymbol import aggregate_symbol_results
from src.evaluation.report_honesty import ReportHonestyError, assert_truthful, find_overclaims


def _honest_negative(symbol, net_pnl, trades=40, adequate=True):
    return {
        "symbol": symbol,
        "net_pnl": float(net_pnl),
        "closed_trades": trades,
        "promotion_allowed": False,
        "promotion_reason": "NEGATIVE_NET_PNL",
        "adequate_sample": adequate,
    }


def test_aggregate_empty_raises():
    with pytest.raises(ValueError):
        aggregate_symbol_results([])


def test_aggregate_negative_symbols_block_promotion():
    results = [_honest_negative("BTCUSDT", -100.0), _honest_negative("ETHUSDT", -50.0)]
    agg = aggregate_symbol_results(results)
    assert agg["selection_blocked"] is True
    assert agg["aggregate_promotion_allowed"] is False
    assert agg["aggregate_promotion_reason"] == "POSITIVE_EVIDENCE_REQUIRED"
    assert agg["overall_net_pnl"] == -150.0
    assert agg["overall_closed_trades"] == 80
    assert agg["robust_edge"] is False
    # The aggregate itself is truthful (no overclaim).
    assert find_overclaims(agg) == []
    assert_truthful(agg)


def test_aggregate_refuses_overclaiming_symbol():
    # A per-symbol result that smuggles a nested selection overclaim must be
    # refused before any aggregate is emitted (fail closed). The recursive
    # guard (Phase 18) catches it whether the key is top-level or nested.
    bad = _honest_negative("BTCUSDT", -100.0)
    bad["detail"] = {"winner": True}
    with pytest.raises(ReportHonestyError):
        aggregate_symbol_results([bad, _honest_negative("ETHUSDT", -50.0)])


def test_aggregate_selection_blocked_forces_block_even_if_all_positive():
    # Even if every symbol were positive, selection being blocked keeps the
    # aggregate promotion gate False. Positive measurement is never, by itself,
    # a go-live license in this repo.
    pos = {
        "symbol": "BTCUSDT",
        "net_pnl": 100.0,
        "closed_trades": 40,
        "promotion_allowed": False,
        "promotion_reason": "SELECTION_BLOCKED",
        "adequate_sample": True,
    }
    agg = aggregate_symbol_results([pos, dict(pos, symbol="ETHUSDT", net_pnl=20.0)])
    assert agg["selection_blocked"] is True
    assert agg["aggregate_promotion_allowed"] is False
    assert agg["overall_net_pnl"] == 120.0  # positive sum, but gate stays blocked
    assert_truthful(agg)


def test_aggregate_passes_truthful_guard_on_honest_input():
    results = [
        _honest_negative("BTCUSDT", -100.0),
        _honest_negative("ETHUSDT", -50.0),
        _honest_negative("SOLUSDT", -10.0),
    ]
    agg = aggregate_symbol_results(results)
    # No forbidden promotion/winner/promotion keys, verdicts, or profitability
    # contradictions anywhere in the aggregate (including nested per_symbol).
    assert find_overclaims(agg) == []
    assert_truthful(agg)  # must not raise
