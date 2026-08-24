import asyncio

from src.agent.context import PortfolioView, build_context
from src.agent.cycle import run_cycle
from src.agentic_engine import Policy
from src.market.models import Candle, MarketSnapshot
from src.providers.fake import FakeProvider
from src.providers.ports import ProviderResponse


def snapshot():
    return MarketSnapshot(
        "BTCUSDT", 64000, 63990, 64010, 0.0001, 1000, 10000, 10000,
        (Candle("1m", 63900, 64100, 63800, 64000, 10, 10000),),
    ).with_hash()


def policy(kill_switch=False):
    return Policy(frozenset({"BTCUSDT"}), 3, 25, 20, 3, kill_switch=kill_switch)


def response(action="ENTER"):
    return ProviderResponse(
        status="OK",
        content=(
            '{"decision_id":"decision-1234","action":"%s","symbol":"BTCUSDT",'
            '"side":"BUY","entry":64000,"stop_loss":63500,"take_profit":65000,'
            '"leverage":2,"max_notional_usd":20,"valid_until_ms":20000,'
            '"thesis":"trend","invalidation":"below stop"}'
        ) % action,
    )


def test_cycle_approves_valid_agent_decision():
    result = asyncio.run(run_cycle(FakeProvider([response()]), snapshot(), PortfolioView(), policy(), 10500))
    assert result.status == "APPROVED"
    assert result.reason == "APPROVED"
    assert result.context_id


def test_cycle_parks_stale_market_before_provider_call():
    provider = FakeProvider([response()])
    result = asyncio.run(run_cycle(provider, snapshot(), PortfolioView(), policy(), 14001))
    assert result.status == "PARKED"
    assert result.reason == "STALE_MARKET_DATA"
    assert provider.calls == 0


def test_cycle_rejects_provider_malformed_response():
    provider = FakeProvider([ProviderResponse(status="OK", content="bad")])
    result = asyncio.run(run_cycle(provider, snapshot(), PortfolioView(), policy(), 10500))
    assert result.status == "NO_DECISION"
    assert result.reason.startswith("DECISION_PARSE:")


def test_cycle_cannot_bypass_kill_switch():
    result = asyncio.run(run_cycle(FakeProvider([response()]), snapshot(), PortfolioView(), policy(True), 10500))
    assert result.status == "REJECTED"
    assert result.reason == "KILL_SWITCH"
