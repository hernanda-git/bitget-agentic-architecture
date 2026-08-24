import asyncio

from src.agent.context import PortfolioView
from src.agent.runner import CycleRunner
from src.agentic_engine import Policy
from src.market.models import Candle, MarketSnapshot
from src.providers.fake import FakeProvider
from src.providers.ports import ProviderResponse


def snapshot(ts=10000):
    return MarketSnapshot(
        "BTCUSDT", 64000, 63990, 64010, 0.0001, 1000, ts, ts,
        (Candle("1m", 63900, 64100, 63800, 64000, 10, ts),),
    ).with_hash()


def payload():
    return ProviderResponse("OK", '{"decision_id":"decision-1234","action":"HOLD","symbol":"BTCUSDT","side":"NONE","entry":null,"stop_loss":null,"take_profit":null,"leverage":1,"max_notional_usd":1,"valid_until_ms":20000,"thesis":"hold","invalidation":"none"}')


def test_runner_deduplicates_snapshot():
    provider = FakeProvider([payload(), payload()])
    runner = CycleRunner(provider, Policy(frozenset({"BTCUSDT"}), 3, 25, 20, 3, kill_switch=False))
    first = asyncio.run(runner.run_once(snapshot(), PortfolioView(), 10500))
    second = asyncio.run(runner.run_once(snapshot(), PortfolioView(), 10500))
    assert first.status == "APPROVED"
    assert second.reason == "DUPLICATE_CYCLE"
    assert provider.calls == 1


async def _overlap():
    class Blocking(FakeProvider):
        async def decide(self, context):
            self.calls += 1
            await asyncio.sleep(0.02)
            return payload()
    provider = Blocking([])
    runner = CycleRunner(provider, Policy(frozenset({"BTCUSDT"}), 3, 25, 20, 3, kill_switch=False))
    snap = snapshot()
    return await asyncio.gather(
        runner.run_once(snap, PortfolioView(), 10500),
        runner.run_once(snap, PortfolioView(), 10500),
    ), provider


def test_runner_skips_overlapping_cycle():
    results, provider = asyncio.run(_overlap())
    assert sorted(result.reason for result in results) == ["HOLD", "OVERLAPPING_CYCLE"]
    assert provider.calls == 1
