import asyncio

from src.providers.fake import FakeProvider
from src.providers.ports import AgentContext, ProviderResponse


def test_provider_receives_only_structured_context():
    provider = FakeProvider([ProviderResponse(status="OK", content='{"action":"HOLD"}')])
    context = AgentContext("ctx-1", {"symbol": "BTCUSDT"}, {"positions": []}, {"max": 1})
    response = asyncio.run(provider.decide(context))
    assert response.status == "OK"
    assert provider.calls == 1
    assert provider.context_ids == ["ctx-1"]


def test_provider_failure_is_explicit():
    provider = FakeProvider([])
    context = AgentContext("ctx-2", {}, {}, {})
    response = asyncio.run(provider.decide(context))
    assert response.status == "NO_DECISION"
    assert response.error_code == "EXHAUSTED"
