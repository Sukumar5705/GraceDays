from .base import AgentTurn, LLMProvider, ToolCall
from .mock import MockProvider
from .openai_compatible import OpenAICompatibleProvider


def create_provider(settings):
    if settings.llm_provider == "mock":
        return MockProvider()
    return OpenAICompatibleProvider(
        api_key=settings.llm_api_key or "",
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
    )


__all__ = ["AgentTurn", "LLMProvider", "ToolCall", "MockProvider", "OpenAICompatibleProvider", "create_provider"]
