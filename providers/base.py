from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from core.cancellation import CancelToken

from .types import LLMResponse, LLMStreamChunk


@runtime_checkable
class LLMProvider(Protocol):
    """LLM provider interface."""

    name: str
    model: str

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> LLMResponse:
        """Send messages and return a unified LLMResponse.

        `cancel_token` is cooperative (A4 batch 3): a streaming provider can be
        interrupted mid-response, a non-streaming one only avoids retrying.
        """
        ...

    def complete_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> Iterator[LLMStreamChunk]:
        """Stream a unified sequence of response chunks."""
        ...

    def get_name(self) -> str:
        """Return provider name."""
        ...
