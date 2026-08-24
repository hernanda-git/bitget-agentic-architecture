"""Fail-closed provider circuit with bounded async calls."""
from __future__ import annotations

import asyncio
from typing import Any

from .ports import AgentContext, AgentProvider, ProviderResponse


class ProviderCircuit:
    def __init__(self, provider: AgentProvider, timeout_seconds: float = 8.0,
                 failure_threshold: int = 3) -> None:
        self.provider = provider
        self.timeout_seconds = max(float(timeout_seconds), 0.0)
        self.failure_threshold = max(int(failure_threshold), 1)
        self.failures = 0
        self.is_open = False

    async def decide(self, context: AgentContext) -> ProviderResponse:
        if self.is_open:
            return ProviderResponse("NO_DECISION", error_code="PROVIDER_CIRCUIT_OPEN")
        try:
            response = await asyncio.wait_for(self.provider.decide(context), self.timeout_seconds)
        except asyncio.TimeoutError:
            return self._failure("PROVIDER_TIMEOUT")
        except Exception:
            return self._failure("PROVIDER_ERROR")
        if not isinstance(response, ProviderResponse):
            return self._failure("PROVIDER_MALFORMED")
        if response.status != "OK":
            return self._failure(response.error_code or response.status or "PROVIDER_ERROR")
        self.failures = 0
        return response

    async def health_check(self) -> bool:
        """Perform a new provider health call before closing the breaker."""
        health = getattr(self.provider, "health", None)
        if not callable(health):
            return False
        try:
            result = await asyncio.wait_for(health(), self.timeout_seconds)
        except Exception:
            return False
        if result:
            self.failures = 0
            self.is_open = False
            return True
        return False

    def _failure(self, code: str) -> ProviderResponse:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.is_open = True
        return ProviderResponse("NO_DECISION", error_code=code)

    @property
    def circuit_open(self) -> bool:
        return self.is_open
