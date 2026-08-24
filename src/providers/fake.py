"""Deterministic fake provider for offline tests and paper runs."""
from __future__ import annotations

from collections.abc import Iterable

from src.providers.ports import AgentContext, ProviderResponse


class FakeProvider:
    def __init__(self, responses: Iterable[ProviderResponse]):
        self._responses = iter(responses)
        self.calls = 0
        self.context_ids: list[str] = []

    async def decide(self, context: AgentContext) -> ProviderResponse:
        self.calls += 1
        self.context_ids.append(context.context_id)
        try:
            return next(self._responses)
        except StopIteration:
            return ProviderResponse(status="NO_DECISION", error_code="EXHAUSTED")
