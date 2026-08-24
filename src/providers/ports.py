"""Provider-neutral contracts. Providers never receive venue or signing objects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentContext:
    context_id: str
    snapshot: dict[str, Any]
    portfolio: dict[str, Any]
    policy_view: dict[str, Any]
    recent_events: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ProviderResponse:
    status: str
    content: str = ""
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    error_code: str = ""


class AgentProvider(Protocol):
    async def decide(self, context: AgentContext) -> ProviderResponse:
        """Return raw structured content or an explicit provider failure."""
