import asyncio

from src.agent.context import PortfolioView
from src.agentic_engine import Policy
from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.market.models import MarketSnapshot
from src.providers.fake import FakeProvider
from src.providers.ports import ProviderResponse
from src.runtime.paper_runtime import AutonomousPaperRuntime


def snapshot(ts=10000):
    return MarketSnapshot("BTCUSDT", 100, 99.9, 100.1, 0, 10, ts, ts).with_hash()


def response(action="ENTER"):
    return ProviderResponse("OK", '{"decision_id":"decision-1234","action":"%s","symbol":"BTCUSDT","side":"BUY","entry":100,"stop_loss":95,"take_profit":110,"leverage":1,"max_notional_usd":20,"valid_until_ms":20000,"thesis":"t","invalidation":"i"}' % action)


def policy():
    return Policy(frozenset({"BTCUSDT"}), 3, 25, 20, 3, kill_switch=False)


def test_runtime_executes_enter_and_records_terminal_trace(tmp_path):
    ledger = EventLedger(tmp_path / "events.sqlite3")
    exchange = FakeExchange()
    runtime = AutonomousPaperRuntime(FakeProvider([response()]), policy(), ledger, exchange)
    result = asyncio.run(runtime.process(snapshot(), PortfolioView(), 10500))
    assert result["status"] == "EXECUTED"
    assert len(exchange.fills) == 1
    assert ledger.cycle_status(result["cycle_id"]) == "EXECUTED"


def test_runtime_provider_timeout_never_places_order(tmp_path):
    class Slow:
        async def decide(self, context):
            await asyncio.sleep(0.05)
    ledger = EventLedger(tmp_path / "events.sqlite3")
    exchange = FakeExchange()
    runtime = AutonomousPaperRuntime(Slow(), policy(), ledger, exchange, provider_timeout_seconds=0.001)
    result = asyncio.run(runtime.process(snapshot(), PortfolioView(), 10500))
    assert result["status"] in {"NO_DECISION", "PARKED_PROVIDER"}
    assert exchange.fills == []


def test_provider_cannot_change_kill_switch_or_access_exchange(tmp_path):
    class Inspecting:
        async def decide(self, context):
            assert not hasattr(context, "place_order")
            assert "kill_switch" in context.policy_view
            return response("HOLD")
    runtime = AutonomousPaperRuntime(Inspecting(), policy(), EventLedger(tmp_path / "e.db"), FakeExchange())
    assert asyncio.run(runtime.process(snapshot(), PortfolioView(), 10500))["status"] == "HELD"


def test_runtime_parks_entries_when_a_breaker_is_open(tmp_path):
    from src.policy.breakers import BreakerRegistry, BreakerStore

    ledger = EventLedger(tmp_path / "events.sqlite3")
    exchange = FakeExchange()
    reg = BreakerRegistry(BreakerStore(tmp_path / "breakers.json"))
    # Any open breaker (here the resource breaker) must park new entries.
    reg.trip("resource", "resource pressure: LOW_AVAILABLE_MEMORY")
    runtime = AutonomousPaperRuntime(FakeProvider([response()]), policy(), ledger, exchange, breakers=reg)
    result = asyncio.run(runtime.process(snapshot(), PortfolioView(), 10500))
    assert result["status"] == "PARKED"
    assert result["reason"] == "BREAKER_OPEN"
    # Fail-closed: no order is placed while a breaker is open.
    assert exchange.fills == []
    assert ledger.cycle_status(result["cycle_id"]) == "PARKED"


def test_runtime_executes_when_no_breaker_open(tmp_path):
    # Sanity: omitting the breakers registry leaves the execution path unchanged.
    ledger = EventLedger(tmp_path / "events.sqlite3")
    exchange = FakeExchange()
    runtime = AutonomousPaperRuntime(FakeProvider([response()]), policy(), ledger, exchange)
    result = asyncio.run(runtime.process(snapshot(), PortfolioView(), 10500))
    assert result["status"] == "EXECUTED"
    assert len(exchange.fills) == 1


def test_resource_pressure_end_to_end_parks_entries(tmp_path):
    from scripts.resource_guard import GuardPolicy, ResourceSnapshot
    from src.policy.breakers import BreakerRegistry, BreakerStore
    from src.runtime.resource_monitor import ResourceMonitor

    ledger = EventLedger(tmp_path / "events.sqlite3")
    exchange = FakeExchange()
    reg = BreakerRegistry(BreakerStore(tmp_path / "breakers.json"))
    # Host resource pressure under a strict policy trips the resource breaker.
    mon = ResourceMonitor(
        policy=GuardPolicy(min_available_memory_mb=10**9),
        snapshot_source=lambda: ResourceSnapshot(
            available_memory_bytes=1, total_memory_bytes=4 * 1024**3,
            swap_used_bytes=0, swap_total_bytes=2 * 1024**3,
            disk_free_bytes=30 * 1024**3, disk_total_bytes=64 * 1024**3,
            disk_used_percent=40.0, inode_free_percent=50.0),
    )
    mon.attach(reg)
    mon.tick(1000)
    assert reg.is_open("resource") is True
    runtime = AutonomousPaperRuntime(FakeProvider([response()]), policy(), ledger, exchange, breakers=reg)
    result = asyncio.run(runtime.process(snapshot(), PortfolioView(), 1050))
    assert result["status"] == "PARKED"
    assert result["reason"] == "BREAKER_OPEN"
    assert exchange.fills == []
