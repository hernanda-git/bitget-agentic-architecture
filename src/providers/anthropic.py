"""Anthropic Messages API adapter with fail-closed provider behavior."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.providers.ports import AgentContext, AgentProvider, ProviderResponse

log = logging.getLogger(__name__)


class AnthropicProvider(AgentProvider):
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com",
                 timeout_seconds: float = 8.0, max_retries: int = 1,
                 circuit_breaker_failures: int = 3, prompt_version: str = "v1",
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if not model:
            raise ValueError("model is required")
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = min(max(max_retries, 0), 2)
        self.circuit_breaker_failures = max(circuit_breaker_failures, 1)
        self.prompt_version = prompt_version
        self._failures = 0
        self._transport = transport

    @property
    def circuit_open(self) -> bool:
        return self._failures >= self.circuit_breaker_failures

    def _context_content(self, context: AgentContext) -> str:
        return json.dumps({
            "context_id": context.context_id,
            "snapshot": context.snapshot,
            "portfolio": context.portfolio,
            "policy_view": context.policy_view,
            "recent_events": context.recent_events,
        }, separators=(",", ":"), sort_keys=True)

    async def decide(self, context: AgentContext) -> ProviderResponse:
        if self.circuit_open:
            return ProviderResponse(status="PARK", provider="anthropic", model=self.model,
                                    prompt_version=self.prompt_version,
                                    error_code="PROVIDER_CIRCUIT_OPEN")
        payload = {
            "model": self.model,
            "max_tokens": 1200,
            "temperature": 0,
            "system": "Return only the strict autonomous agent decision JSON contract.",
            "messages": [{"role": "user", "content": self._context_content(context)}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self._transport) as client:
                response = None
                for attempt in range(self.max_retries + 1):
                    try:
                        response = await client.post(f"{self.base_url}/v1/messages",
                                                     headers=headers, json=payload)
                    except (httpx.TimeoutException, httpx.TransportError):
                        if attempt >= self.max_retries:
                            raise
                        continue
                    if response.status_code >= 500 and attempt < self.max_retries:
                        continue
                    break
            if response is None:
                raise httpx.TransportError("no provider response")
            if response.status_code != 200:
                self._record_failure("HTTP_STATUS")
                code = "PROVIDER_QUOTA" if response.status_code == 429 else "PROVIDER_HTTP"
                return ProviderResponse(status="NO_DECISION", provider="anthropic", model=self.model,
                                        prompt_version=self.prompt_version, error_code=code)
            if len(response.content) > 256_000:
                self._record_failure("RESPONSE_TOO_LARGE")
                return ProviderResponse(status="NO_DECISION", provider="anthropic", model=self.model,
                                        prompt_version=self.prompt_version, error_code="RESPONSE_TOO_LARGE")
            data = response.json()
            content = self._extract_text(data)
            if content is None:
                self._record_failure("MALFORMED")
                return ProviderResponse(status="NO_DECISION", provider="anthropic", model=self.model,
                                        prompt_version=self.prompt_version, error_code="PROVIDER_MALFORMED")
            self._failures = 0
            return ProviderResponse(status="OK", content=content, provider="anthropic",
                                    model=self.model, prompt_version=self.prompt_version)
        except (httpx.TimeoutException, httpx.TransportError, ValueError, KeyError, TypeError) as exc:
            self._record_failure(type(exc).__name__)
            log.warning("provider request failed type=%s", type(exc).__name__)
            return ProviderResponse(status="NO_DECISION", provider="anthropic", model=self.model,
                                    prompt_version=self.prompt_version, error_code="PROVIDER_UNAVAILABLE")

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str | None:
        content = data.get("content")
        if not isinstance(content, list) or not content:
            return None
        first = content[0]
        if not isinstance(first, dict) or first.get("type") != "text":
            return None
        text = first.get("text")
        return text if isinstance(text, str) and text else None

    def _record_failure(self, reason: str) -> None:
        self._failures += 1
        log.warning("provider failure reason=%s consecutive=%s", reason, self._failures)
