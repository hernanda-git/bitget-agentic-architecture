import asyncio
import json

from src.agent.context import PortfolioView
from src.agentic_engine import Policy
from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.market.models import MarketSnapshot
from src.providers.fake import FakeProvider
from src.providers.ports import ProviderResponse
from src.runtime.canonical import CanonicalOfflineRuntime


def snapshot(symbol="BTCUSDT", observed=10_000, source=10_000):
    return MarketSnapshot(symbol, 100, 99.9, 100.1, 0, 1, observed, source).with_hash()


def response(action="ENTER", symbol="BTCUSDT"):
    body = {
        "decision_id": "canonical-decision-001", "action": action, "symbol": symbol,
        "side": "BUY" if action != "HOLD" else "NONE",
        "entry": 100 if action != "HOLD" else None,
        "stop_loss": 95 if action != "HOLD" else None,
        "take_profit": 110 if action != "HOLD" else None,
        "leverage": 1, "max_notional_usd": 20, "valid_until_ms": 20_000,
        "thesis": "test", "invalidation": "stop",
    }
    return ProviderResponse("OK", json.dumps(body))


def policy(**kwargs):
    values = dict(allow_symbols=frozenset({"BTCUSDT"}), max_leverage=3,
                  max_position_notional_usd=25, max_spread_bps=30,
                  max_snapshot_age_seconds=3, kill_switch=False)
    values.update(kwargs)
    return Policy(**values)


def paper(tmp_path, provider, **policy_overrides):
    return CanonicalOfflineRuntime.paper(
        provider=provider, policy=policy(**policy_overrides),
        ledger=EventLedger(tmp_path / "ledger.sqlite3"), exchange=FakeExchange(),
    )


def test_canonical_paper_lifecycle_handles_hold(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    runtime = CanonicalOfflineRuntime.paper(FakeProvider([response("HOLD")]), policy(), ledger, FakeExchange())

    result = asyncio.run(runtime.process(snapshot(), PortfolioView(), 10_500))

    assert result["status"] == "HELD"
    assert not ledger.table_rows("orders")
    assert [event["event_type"] for event in ledger.all()][-1] == "CYCLE_TERMINAL"


def test_canonical_enter_has_one_terminal_and_duplicate_has_no_order(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    runtime = CanonicalOfflineRuntime.paper(FakeProvider([response(), response()]), policy(), ledger, FakeExchange())

    first = asyncio.run(runtime.process(snapshot(), PortfolioView(), 10_500))
    duplicate = asyncio.run(runtime.process(snapshot(), PortfolioView(), 10_500))

    assert first["status"] == "EXECUTED"
    assert duplicate == {"status": "SKIPPED", "reason": "DUPLICATE_CYCLE", "cycle_id": snapshot().snapshot_hash}
    assert len(runtime.paper_runtime.exchange.orders) == 1
    terminals = [e for e in ledger.all() if e["event_type"] == "CYCLE_TERMINAL"]
    assert len(terminals) == 1


def test_canonical_paper_parks_stale_snapshot(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    runtime = CanonicalOfflineRuntime.paper(FakeProvider([response()]), policy(), ledger, FakeExchange())

    result = asyncio.run(runtime.process(snapshot(observed=1_000, source=1_000), PortfolioView(), 10_000))

    assert result["status"] == "PARKED"
    assert result["reason"] == "STALE_MARKET_DATA"
    assert not ledger.table_rows("orders")


def test_canonical_paper_preserves_provider_failure_and_policy_rejection(tmp_path):
    failure_ledger = EventLedger(tmp_path / "failure.sqlite3")
    failure = CanonicalOfflineRuntime.paper(
        FakeProvider([ProviderResponse("ERROR", error_code="TIMEOUT")]), policy(), failure_ledger, FakeExchange())
    rejected_ledger = EventLedger(tmp_path / "rejected.sqlite3")
    rejected = CanonicalOfflineRuntime.paper(
        FakeProvider([response(symbol="ETHUSDT")]),
        policy(allow_symbols=frozenset({"BTCUSDT", "ETHUSDT"})), rejected_ledger, FakeExchange())

    failure_result = asyncio.run(failure.process(snapshot(), PortfolioView(), 10_500))
    rejected_result = asyncio.run(rejected.process(snapshot(), PortfolioView(), 10_500))

    assert failure_result["status"] == "NO_DECISION"
    assert failure_result["reason"] == "TIMEOUT"
    assert rejected_result["status"] == "REJECTED"
    assert rejected_result["reason"] == "MARKET_SYMBOL_MISMATCH"
    assert not failure_ledger.table_rows("orders")
    assert not rejected_ledger.table_rows("orders")


def test_fixture_shadow_uses_canonical_lifecycle_without_paper_execution(tmp_path):
    ledger = EventLedger(tmp_path / "shadow.sqlite3")
    runtime = CanonicalOfflineRuntime.fixture_shadow(ledger)

    result = asyncio.run(runtime.process(snapshot(), PortfolioView(), 10_500))

    assert result["status"] == "SHADOW_ONLY"
    assert result["mode"] == "fixture-shadow"
    assert result["orders_placed"] == 0
    assert result["network_calls"] == 0
    assert not ledger.table_rows("orders")
