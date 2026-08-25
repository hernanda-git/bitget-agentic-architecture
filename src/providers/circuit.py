"""Fail-closed provider circuit with bounded async calls."""
from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
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
        self.telemetry: list[dict[str, Any]] = []

    async def decide(self, context: AgentContext) -> ProviderResponse:
        started = time.perf_counter()
        if self.is_open:
            response = ProviderResponse("NO_DECISION", error_code="PROVIDER_CIRCUIT_OPEN")
            self._record(response, started)
            return response
        try:
            response = await asyncio.wait_for(self.provider.decide(context), self.timeout_seconds)
        except asyncio.TimeoutError:
            response = self._failure("PROVIDER_TIMEOUT")
            self._record(response, started)
            return response
        except Exception:
            response = self._failure("PROVIDER_ERROR")
            self._record(response, started)
            return response
        if not isinstance(response, ProviderResponse):
            failed = self._failure("PROVIDER_MALFORMED")
            self._record(failed, started)
            return failed
        if response.status != "OK":
            failed = self._failure(response.error_code or response.status or "PROVIDER_ERROR")
            self._record(failed, started)
            return failed
        self.failures = 0
        self._record(response, started)
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

    def _record(self, response: ProviderResponse, started: float) -> None:
        content = response.content or ""
        self.telemetry.append({"provider": response.provider, "model": response.model,
            "prompt_version": response.prompt_version, "latency_ms": (time.perf_counter() - started) * 1000,
            "status": response.status, "error_code": response.error_code,
            "response_size": len(content.encode()), "decision_hash": hashlib.sha256(content.encode()).hexdigest() if content else ""})

    def _failure(self, code: str) -> ProviderResponse:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.is_open = True
        return ProviderResponse("NO_DECISION", error_code=code)

    @property
    def circuit_open(self) -> bool:
        return self.is_open
