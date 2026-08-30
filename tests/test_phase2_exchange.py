import pytest

from src.execution.ports import ExchangePort, MarketEventPort
from src.execution.specifications import FeeSchedule, FundingSchedule, VenueSpecification, VenueRuleError
from src.execution.fake_exchange import FakeExchange, OrderRequest, OrderStatus
from src.simulation.events import MarketEvent
from src.accounting.pnl import TradeAccounting, calculate_trade


def venue():
    return VenueSpecification(
        price_tick=0.1, quantity_step=0.01, minimum_quantity=0.01,
        minimum_notional=1.0, contract_multiplier=1.0,
        fee_schedule=FeeSchedule(maker_bps=2, taker_bps=5),
        funding_schedule=FundingSchedule(rate_per_event=0.001), max_leverage=5,
        allowed_margin_modes=frozenset({"isolated", "cross"}),
    )


def test_ports_are_runtime_checkable_and_exchange_has_typed_operations():
    exchange = FakeExchange(venue=venue(), initial_balance=1000)
    assert isinstance(exchange, ExchangePort)
    assert isinstance(exchange, MarketEventPort)
    for name in ("submit_order", "cancel_order", "read_order", "read_fills",
                 "read_positions", "read_open_orders", "read_balance", "apply_market_event"):
        assert callable(getattr(exchange, name))


def test_venue_rules_reject_values_not_exactly_representable():
    with pytest.raises(VenueRuleError, match="price tick"):
        venue().validate_order(symbol="BTCUSDT", quantity=0.01, price=100.03)
    with pytest.raises(VenueRuleError, match="minimum notional"):
        venue().validate_order(symbol="BTCUSDT", quantity=0.01, price=10)


def test_market_limit_partial_expiry_and_realistic_states():
    exchange = FakeExchange(venue=venue(), initial_balance=1000, partial_fill_ratio=0.4)
    market = exchange.submit_order(OrderRequest("m1", "BTCUSDT", "BUY", 1, None))
    assert market.status is OrderStatus.FILLED
    limit = exchange.submit_order(OrderRequest("l1", "BTCUSDT", "BUY", 1, 99.0, time_in_force="GTC"))
    assert limit.status is OrderStatus.NEW
    exchange.apply_market_event(MarketEvent("BTCUSDT", bid=98.9, ask=99.0, mark=98.95, sequence=1))
    assert exchange.read_order("l1").status is OrderStatus.PARTIALLY_FILLED
    exchange.apply_market_event(MarketEvent("BTCUSDT", bid=98.8, ask=98.9, mark=98.85, sequence=2))
    assert exchange.read_order("l1").status is OrderStatus.FILLED
    exp = exchange.submit_order(OrderRequest("exp", "BTCUSDT", "BUY", 1, 90, time_in_force="IOC"))
    assert exp.status is OrderStatus.EXPIRED


def test_duplicate_rejection_slippage_spread_and_reduce_only():
    exchange = FakeExchange(venue=venue(), initial_balance=1000, slippage_bps=10)
    first = exchange.submit_order(OrderRequest("dup", "BTCUSDT", "BUY", 1, None))
    assert exchange.submit_order(OrderRequest("dup", "BTCUSDT", "BUY", 1, None)) == first
    with pytest.raises(ValueError, match="duplicate"):
        exchange.submit_order(OrderRequest("dup", "BTCUSDT", "SELL", 2, None))
    reject = exchange.submit_order(OrderRequest("bad", "BTCUSDT", "BUY", 1, 100.03))
    assert reject.status is OrderStatus.REJECTED
    assert exchange.read_order("bad").reason
    reduce = exchange.submit_order(OrderRequest("reduce", "BTCUSDT", "SELL", 0.5, None, reduce_only=True))
    assert reduce.status is OrderStatus.FILLED
    no_reduce = exchange.submit_order(OrderRequest("reduce-empty", "BTCUSDT", "SELL", 5, None, reduce_only=True))
    assert no_reduce.status is OrderStatus.REJECTED


def test_trade_accounting_separates_spread_and_execution_slippage():
    exchange = FakeExchange(venue=venue(), initial_balance=1000, slippage_bps=10)
    exchange.market_prices["BTCUSDT"] = (99.0, 101.0, 100.0)
    entry = exchange.submit_order(OrderRequest("accounted-entry", "BTCUSDT", "BUY", 1, None))
    assert entry.status is OrderStatus.FILLED
    exchange.market_prices["BTCUSDT"] = (109.0, 111.0, 110.0)
    exit_order = exchange.submit_order(
        OrderRequest("accounted-exit", "BTCUSDT", "SELL", 1, None, reduce_only=True)
    )

    assert exit_order.status is OrderStatus.FILLED
    trade = exchange.closed_trades[-1]
    assert trade["gross_pnl"] == pytest.approx(10.0)
    assert trade["spread_cost"] == pytest.approx(2.0)
    assert trade["slippage_cost"] == pytest.approx(0.21)
    assert trade["net_pnl"] == pytest.approx(
        10.0 - trade["entry_fee"] - trade["exit_fee"] - 2.0 - 0.21
    )


def test_cancel_request_and_cancelled_state():
    exchange = FakeExchange(venue=venue(), initial_balance=1000)
    exchange.submit_order(OrderRequest("rest", "BTCUSDT", "BUY", 1, 90))
    assert exchange.cancel_order("rest").status is OrderStatus.CANCELLED


def test_protection_gap_through_stop_fires_exactly_once():
    exchange = FakeExchange(venue=venue(), initial_balance=1000)
    exchange.submit_order(OrderRequest("entry", "BTCUSDT", "BUY", 1, None))
    exchange.set_protection("BTCUSDT", stop_loss=95, take_profit=110)
    events = exchange.apply_market_event(MarketEvent("BTCUSDT", bid=80, ask=81, mark=80, sequence=1))
    assert [e.kind for e in events].count("PROTECTION_TRIGGERED") == 1
    assert not exchange.read_positions()
    assert exchange.apply_market_event(MarketEvent("BTCUSDT", bid=79, ask=80, mark=79, sequence=2)) == []


def test_protection_fill_uses_executable_quote_without_inventing_slippage():
    exchange = FakeExchange(venue=venue(), initial_balance=1000, fee_bps=0, slippage_bps=0)
    exchange.market_prices["BTCUSDT"] = (99.0, 101.0, 100.0)
    exchange.submit_order(OrderRequest("entry", "BTCUSDT", "BUY", 1, None))
    exchange.set_protection("BTCUSDT", stop_loss=95, take_profit=110)

    exchange.apply_market_event(
        MarketEvent("BTCUSDT", bid=89.0, ask=91.0, mark=90.0, sequence=1)
    )

    trade = exchange.closed_trades[-1]
    assert exchange.read_fills()[-1].price == pytest.approx(89.0)
    assert trade["spread_cost"] == pytest.approx(2.0)
    assert trade["slippage_cost"] == pytest.approx(0.0)
    assert trade["net_pnl"] == pytest.approx(-12.0)


def test_negative_funding_rate_reverses_payment_direction():
    long_exchange = FakeExchange(fee_bps=0)
    long_exchange.submit_order(OrderRequest("long-open", "BTCUSDT", "BUY", 1.0, None))
    long_exchange.apply_market_event(
        MarketEvent("BTCUSDT", bid=99.0, ask=101.0, mark=100.0, sequence=1, funding_rate=-0.001)
    )

    short_exchange = FakeExchange(fee_bps=0)
    short_exchange.submit_order(OrderRequest("short-open", "BTCUSDT", "SELL", 1.0, None))
    short_exchange.apply_market_event(
        MarketEvent("BTCUSDT", bid=99.0, ask=101.0, mark=100.0, sequence=1, funding_rate=-0.001)
    )

    assert long_exchange.read_balance()["funding_paid"] == pytest.approx(0.0)
    assert long_exchange.read_balance()["funding_received"] == pytest.approx(0.1)
    assert short_exchange.read_balance()["funding_paid"] == pytest.approx(0.1)
    assert short_exchange.read_balance()["funding_received"] == pytest.approx(0.0)


def test_closed_trade_includes_funding_accrued_while_position_was_open():
    exchange = FakeExchange(fee_bps=0)
    exchange.submit_order(OrderRequest("open", "BTCUSDT", "BUY", 1.0, None))
    exchange.apply_market_event(
        MarketEvent("BTCUSDT", bid=99.0, ask=101.0, mark=100.0, sequence=1, funding_rate=0.001)
    )
    exchange.market_prices["BTCUSDT"] = (110.0, 110.0, 110.0)
    exchange.submit_order(OrderRequest("close", "BTCUSDT", "SELL", 1.0, None, reduce_only=True))

    trade = exchange.closed_trades[-1]
    assert trade["funding"] == pytest.approx(0.1)
    assert trade["net_pnl"] == pytest.approx(9.9)


def test_funding_accrues_one_realistic_leg_per_settlement():
    """Phase 41: a settlement-aligned event uses the shared funding model and accrues
    exactly one realistic leg, direction-aware. Two distinct settlements accrue two
    legs (no collapse to a single charge)."""
    exchange = FakeExchange(fee_bps=0)
    exchange.submit_order(OrderRequest("open", "BTCUSDT", "BUY", 1.0, None))
    exchange.apply_market_event(
        MarketEvent("BTCUSDT", bid=99.0, ask=101.0, mark=100.0, sequence=1,
                    timestamp_ms=8 * 3600 * 1000, funding_rate=0.0001)
    )
    # Long pays the positive 8h rate once: 1.0 * 100.0 * 0.0001 = 0.01.
    assert exchange.read_balance()["funding_paid"] == pytest.approx(0.01)
    assert exchange.read_balance()["funding_received"] == pytest.approx(0.0)
    # A second distinct settlement accrues a second leg (not a collapse to one).
    exchange.apply_market_event(
        MarketEvent("BTCUSDT", bid=99.0, ask=101.0, mark=100.0, sequence=2,
                    timestamp_ms=16 * 3600 * 1000, funding_rate=0.0001)
    )
    assert exchange.read_balance()["funding_paid"] == pytest.approx(0.02)


def test_funding_non_settlement_event_uses_conservative_per_bar_proxy():
    """Phase 41: synthetic fixtures whose bar timestamps are not settlement-aligned
    still accrue via the conservative per-bar proxy (a fail-closed upper-bound stress
    estimate), never silently dropping funding. This is the fallback, not the
    settlement-accurate path used by real-history replay."""
    exchange = FakeExchange(fee_bps=0)
    exchange.submit_order(OrderRequest("open", "BTCUSDT", "BUY", 1.0, None))
    exchange.apply_market_event(
        MarketEvent("BTCUSDT", bid=99.0, ask=101.0, mark=100.0, sequence=1,
                    timestamp_ms=1 * 3600 * 1000, funding_rate=0.0001)
    )
    # Per-bar proxy: one charge of qty * mark * rate.
    assert exchange.read_balance()["funding_paid"] == pytest.approx(0.01)
    assert exchange.read_balance()["funding_received"] == pytest.approx(0.0)


def test_funding_settlement_short_receives_positive_rate():
    """Phase 41: short at a settlement with a positive rate receives (the mirror)."""
    exchange = FakeExchange(fee_bps=0)
    exchange.submit_order(OrderRequest("open", "BTCUSDT", "SELL", 2.0, None))
    exchange.apply_market_event(
        MarketEvent("BTCUSDT", bid=99.0, ask=101.0, mark=50.0, sequence=1,
                    timestamp_ms=8 * 3600 * 1000, funding_rate=0.0001)
    )
    # Short receives the positive rate: 2.0 * 50.0 * 0.0001 = 0.01 credited.
    assert exchange.read_balance()["funding_paid"] == pytest.approx(0.0)
    assert exchange.read_balance()["funding_received"] == pytest.approx(0.01)


def test_dense_per_bar_funding_accrues_only_at_settlements():
    """Phase 41 anti-overstatement invariant, mirroring the real-replay contract.

    In real replay, ``snapshots_from_dataset`` attaches ``funding_rate`` ONLY to the
    settlement-crossing snapshot (one per settlement), and ``baseline`` forwards that
    snapshot's ``source_ts_ms`` -- an exact 8h boundary -- as the MarketEvent
    timestamp. So a position spanning 48h sees funding-bearing events only at the
    settlement boundaries (8h, 16h, 24h, 32h, 40h within (0, 48h]) and accrues exactly
    5 settlement legs via the shared model, never one per bar. This asserts that
    contract: feed funding only on settlement-timestamped events."""
    exchange = FakeExchange(fee_bps=0)
    exchange.submit_order(OrderRequest("open", "BTCUSDT", "BUY", 1.0, None))
    settlement_hours = [8, 16, 24, 32, 40]  # 8h multiples within (0, 48h]
    for hour in settlement_hours:
        ts = hour * 3600 * 1000  # exact 8h boundary -> is_settlement_timestamp True
        exchange.apply_market_event(
            MarketEvent("BTCUSDT", bid=99.0, ask=101.0, mark=100.0, sequence=hour,
                        timestamp_ms=ts, funding_rate=0.0001)
        )
    # Exactly 5 settlement legs, qty 1, mark 100 => 5 * 1 * 100 * 0.0001 = 0.05.
    assert exchange.read_balance()["funding_paid"] == pytest.approx(5 * 1.0 * 100.0 * 0.0001)
    assert exchange.read_balance()["funding_received"] == pytest.approx(0.0)
    # Far smaller than the old per-bar proxy would have charged on a dense 48-bar series.
    assert exchange.read_balance()["funding_paid"] < 48 * 1.0 * 100.0 * 0.0001


def test_accounting_includes_fees_funding_slippage_and_return_on_margin():
    result = calculate_trade(side="BUY", quantity=1, entry_price=100, exit_price=110,
                             entry_fee=0.05, exit_fee=0.055, funding_paid=0.1,
                             funding_received=0, slippage_cost=0.2, margin=100)
    assert result.gross_pnl == pytest.approx(10)
    assert result.net_pnl == pytest.approx(9.595)
    assert result.return_on_margin == pytest.approx(0.09595)
    assert isinstance(result, TradeAccounting)
