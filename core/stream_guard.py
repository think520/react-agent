"""Stream sanitization guard (AG-0.4).

Wraps a provider stream so that malformed tool-call protocol never leaks into
the agent loop or the user-visible text:

- Tool-call deltas are buffered by index (mirroring the loop) and, at the end
  of the stream, only tool calls with a non-empty name are re-emitted for
  execution.
- A buffered tool call with an empty name but real content is recovered as
  visible text instead of being executed as an unknown tool.
- Empty tool fragments (no id, no name, no arguments) are dropped outright and
  never written back as visible text.
- Stream-level errors are normalized to a typed ProviderError so the loop can
  emit a clean error event instead of a bare exception.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from providers.errors import (
    ProviderConnectionError,
    ProviderError,
    ProviderTimeout,
)
from providers.types import LLMStreamChunk, ToolCall, ToolCallDelta

_MALFORMED_TOOL_PREFIX = "[尝试调用工具，但缺少工具名称"


@dataclass
class _ToolBuffer:
    id: str = ""
    name: str = ""
    arguments: list[str] = field(default_factory=list)


def _recover_as_text(buffer: _ToolBuffer) -> str:
    arguments = "".join(buffer.arguments).strip()
    if arguments:
        try:
            parsed = json.loads(arguments)
            arguments = json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return f"\n\n{_MALFORMED_TOOL_PREFIX}：{arguments}]"
    return f"\n\n{_MALFORMED_TOOL_PREFIX}]"


def guard_stream(chunks: Iterator[LLMStreamChunk]) -> Iterator[LLMStreamChunk]:
    """Yield sanitized chunks from a provider stream.

    Content deltas pass through immediately (streaming is preserved). Tool-call
    deltas are buffered and only resolved when the stream ends, because a name
    may arrive in a later chunk and we must not execute a nameless tool call.
    """
    buffers: dict[int, _ToolBuffer] = {}
    for chunk in chunks:
        if chunk.content_delta:
            yield chunk
        for delta in chunk.tool_call_deltas:
            buffer = buffers.setdefault(delta.index, _ToolBuffer())
            if delta.id:
                buffer.id = delta.id
            if delta.name:
                buffer.name = delta.name
            if delta.arguments:
                buffer.arguments.append(delta.arguments)

    for index in sorted(buffers):
        buffer = buffers[index]
        if buffer.name:
            yield LLMStreamChunk(
                tool_call_deltas=[
                    ToolCallDelta(
                        index=index,
                        id=buffer.id,
                        name=buffer.name,
                        arguments="".join(buffer.arguments),
                    )
                ]
            )
        elif buffer.arguments or buffer.id:
            recovered = _recover_as_text(buffer)
            if recovered:
                yield LLMStreamChunk(content_delta=recovered)
        # else: empty fragment — drop it entirely.


def sanitize_tool_calls(
    tool_calls: list[ToolCall] | None,
    content: str = "",
) -> tuple[list[ToolCall], str]:
    """Sanitize a final (non-streaming) response's tool calls.

    Returns (valid_tool_calls, recovered_text). Tool calls with a non-empty
    name are kept; nameless ones are converted into visible text appended to
    content.
    """
    valid: list[ToolCall] = []
    recovered_parts: list[str] = []
    for call in tool_calls or []:
        name = (call.name or "").strip()
        if name:
            valid.append(call)
        else:
            buffer = _ToolBuffer(id=call.id, arguments=[call.arguments or ""])
            recovered = _recover_as_text(buffer)
            if recovered.strip():
                recovered_parts.append(recovered)
    merged = content or ""
    if recovered_parts:
        merged = (merged + "".join(recovered_parts)).rstrip()
    return valid, merged


class GuardedProvider:
    """Provider facade that sanitizes both streaming and complete responses.

    Exposes the same surface the agent loop expects (name/model/get_name/
    complete/complete_stream) so it can wrap any LLMProvider transparently.
    """

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        if not callable(getattr(provider, "complete_stream", None)):
            # Shadow the guarded stream method so the loop's
            # getattr(provider, "complete_stream", None) probe returns None and
            # falls back to the (still guarded) complete() path.
            self.complete_stream = None  # type: ignore[assignment]

    @property
    def name(self) -> str:
        return str(getattr(self._provider, "name", "") or "")

    @property
    def model(self) -> str:
        return str(getattr(self._provider, "model", "") or "")

    def get_name(self) -> str:
        get_name = getattr(self._provider, "get_name", None)
        if callable(get_name):
            return str(get_name())
        return self.name

    def __getattr__(self, item: str):
        # Transparently forward anything else the loop may reach for.
        return getattr(self._provider, item)

    def complete(self, messages: list[dict], tools: list[dict] | None = None):
        response = self._provider.complete(messages, tools=tools)
        try:
            valid, recovered = sanitize_tool_calls(response.tool_calls, response.content)
            response.tool_calls = valid
            response.content = recovered
        except Exception:
            # Sanitization must never break the response path.
            pass
        return response

    def complete_stream(self, messages: list[dict], tools: list[dict] | None = None):
        try:
            yield from guard_stream(self._provider.complete_stream(messages, tools=tools))
        except (ProviderError, ProviderTimeout, ProviderConnectionError):
            raise
        except Exception as exc:
            raise ProviderError(f"Stream failed: {exc}") from exc
