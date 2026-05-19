from typing import Protocol, runtime_checkable
from .types import LLMResponse


@runtime_checkable
class LLMProvider(Protocol):
    """LLM provider interface."""

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """Send messages and return a unified LLMResponse."""
        ...

    def get_name(self) -> str:
        """Return provider name."""
        ...
