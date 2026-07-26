from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from .types import LLMResponse, LLMStreamChunk


@runtime_checkable
class LLMProvider(Protocol):
    """LLM provider interface."""

    name: str
    model: str

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """Send messages and return a unified LLMResponse."""
        ...

    def complete_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> Iterator[LLMStreamChunk]:
        """Stream a unified sequence of response chunks."""
        ...

    def get_name(self) -> str:
        """Return provider name."""
        ...
