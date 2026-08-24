import asyncio
import json

import httpx

from src.providers.anthropic import AnthropicProvider
from src.providers.ports import AgentContext


CONTEXT = AgentContext("ctx-1", {"symbol": "BTCUSDT"}, {"positions": []}, {"max": 1})


def response_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/v1/messages"
    payload = json.loads(request.content)
    assert payload["temperature"] == 0
    assert "signing" not in payload
    return httpx.Response(200, json={"content": [{"type": "text", "text": '{"action":"HOLD"}'}]})


def test_anthropic_adapter_returns_structured_content_without_exposing_key():
    provider = AnthropicProvider("secret-not-logged", "claude-test", transport=httpx.MockTransport(response_handler))
    result = asyncio.run(provider.decide(CONTEXT))
    assert result.status == "OK"
    assert result.content == '{"action":"HOLD"}'
    assert result.provider == "anthropic"


def test_malformed_response_is_no_decision():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"content": []}))
    provider = AnthropicProvider("key", "claude-test", transport=transport)
    result = asyncio.run(provider.decide(CONTEXT))
    assert result.status == "NO_DECISION"
    assert result.error_code == "PROVIDER_MALFORMED"


def test_provider_circuit_breaker_parks_after_failures():
    transport = httpx.MockTransport(lambda request: httpx.Response(503, json={}))
    provider = AnthropicProvider("key", "claude-test", max_retries=0, circuit_breaker_failures=2, transport=transport)
    first = asyncio.run(provider.decide(CONTEXT))
    second = asyncio.run(provider.decide(CONTEXT))
    third = asyncio.run(provider.decide(CONTEXT))
    assert first.error_code == "PROVIDER_HTTP"
    assert second.error_code == "PROVIDER_HTTP"
    assert third.status == "PARK"
    assert third.error_code == "PROVIDER_CIRCUIT_OPEN"
