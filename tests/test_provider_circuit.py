import asyncio

from src.providers.circuit import ProviderCircuit
from src.providers.ports import AgentContext, ProviderResponse


CONTEXT = AgentContext("ctx", {}, {}, {})


class TimeoutProvider:
    async def decide(self, context):
        await asyncio.sleep(0.05)
        return ProviderResponse("OK", "{}")


class FailingProvider:
    async def decide(self, context):
        raise RuntimeError("offline")

    async def health(self):
        return True


class HealthyProvider:
    async def decide(self, context):
        return ProviderResponse("OK", '{"action":"HOLD"}')


def test_timeout_becomes_no_decision_and_opens_after_threshold():
    circuit = ProviderCircuit(TimeoutProvider(), timeout_seconds=0.001, failure_threshold=2)
    first = asyncio.run(circuit.decide(CONTEXT))
    second = asyncio.run(circuit.decide(CONTEXT))
    third = asyncio.run(circuit.decide(CONTEXT))
    assert first.error_code == "PROVIDER_TIMEOUT"
    assert second.error_code == "PROVIDER_TIMEOUT"
    assert third.error_code == "PROVIDER_CIRCUIT_OPEN"


def test_recovery_requires_fresh_successful_health_call():
    circuit = ProviderCircuit(FailingProvider(), failure_threshold=1)
    asyncio.run(circuit.decide(CONTEXT))
    assert circuit.is_open
    assert asyncio.run(circuit.health_check()) is True
    assert circuit.is_open is False


def test_provider_surface_does_not_expose_exchange_order_method():
    circuit = ProviderCircuit(HealthyProvider())
    assert not hasattr(circuit, "place_order")
