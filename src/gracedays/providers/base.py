from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from gracedays.models import ExtractionCandidate


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentTurn:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    """Providers return proposals and tool requests; application code validates all effects."""

    name: str

    def extract(self, source_text: str) -> ExtractionCandidate: ...

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AgentTurn: ...
