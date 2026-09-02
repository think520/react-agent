"""Canonical scripted LLM provider for tests (R0.3: single-seam LLM mock).

Every test must fake the LLM through this module instead of declaring a
local FakeProvider — one seam to maintain, one place that understands the
`LLMProvider` contract. The provider records every request so tests can
assert on prompts and tool schemas, and supports scripted turns:

- `str`                         → text reply (streamed in chunks)
- `{"tool": name, "args": {}}`  → tool call (optionally with `content`)
- `Exception` instance          → raised when the turn is reached
- `LLMResponse`                 → returned verbatim (complete only)

Usage records are emitted in both modes so downstream usage accounting is
exercised the same way as with real providers.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

from providers.errors import ProviderError
from providers.types import LLMResponse, LLMStreamChunk, ToolCall, ToolCallDelta

DEFAULT_CHUNK_SIZE = 7


class ScriptedProvider:
    """Deterministic LLMProvider double driven by a list of scripted turns."""

    def __init__(
        self,
        turns: Iterable[Any] = (),
        *,
        name: str = "scripted",
        model: str = "scripted-model",
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self.name = name
        self.model = model
        self.chunk_size = chunk_size
        self.turns: list[Any] = list(turns)
        # Requests recorded per call: [{"messages": [...], "tools": [...]}]
        self.requests: list[dict[str, Any]] = []
        self._call_index = 0

    # -- scripting helpers -------------------------------------------------

    def queue(self, *turns: Any) -> None:
        self.turns.extend(turns)

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def last_messages(self) -> list[dict] | None:
        return self.requests[-1]["messages"] if self.requests else None

    # -- LLMProvider contract ----------------------------------------------

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        turn = self._record_and_take(messages, tools)
        if isinstance(turn, Exception):
            raise turn
        if isinstance(turn, LLMResponse):
            return self._with_identity(turn)
        if isinstance(turn, dict) and "tool" in turn:
            call = ToolCall(
                id=f"call_{self._call_index:03d}",
                name=turn["tool"],
                arguments=json.dumps(turn.get("args", {}), ensure_ascii=False),
            )
            return LLMResponse(
                content=turn.get("content", ""),
                tool_calls=[call],
                provider=self.name,
                model=self.model,
                usage=self._usage(len(turn.get("content", ""))),
            )
        text = turn if isinstance(turn, str) else json.dumps(turn, ensure_ascii=False)
        return LLMResponse(content=text, provider=self.name, model=self.model, usage=self._usage(len(text)))

    def complete_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> Iterator[LLMStreamChunk]:
        turn = self._record_and_take(messages, tools)
        if isinstance(turn, Exception):
            raise turn
        tool_spec: dict | None = turn if isinstance(turn, dict) and "tool" in turn else None
        text = turn if isinstance(turn, str) else (turn.get("content", "") if isinstance(turn, dict) else json.dumps(turn, ensure_ascii=False))
        request_id = f"req_{self._call_index:03d}"
        emitted = 0
        for start in range(0, len(text), self.chunk_size):
            yield LLMStreamChunk(content_delta=text[start : start + self.chunk_size], request_id=request_id)
            emitted += self.chunk_size
        if tool_spec is not None:
            yield LLMStreamChunk(
                tool_call_deltas=[
                    ToolCallDelta(
                        index=0,
                        id=f"call_{self._call_index:03d}",
                        name=tool_spec["tool"],
                        arguments=json.dumps(tool_spec.get("args", {}), ensure_ascii=False),
                    )
                ],
                request_id=request_id,
            )
        yield LLMStreamChunk(usage=self._usage(max(emitted, len(text))), request_id=request_id)

    def get_name(self) -> str:
        return f"{self.name}/{self.model}"

    # -- internals ----------------------------------------------------------

    def _record_and_take(self, messages: list[dict], tools: list[dict] | None) -> Any:
        self._call_index += 1
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.turns:
            raise ProviderError(
                f"ScriptedProvider ran out of turns at call {self._call_index}; queue more turns in the test"
            )
        return self.turns.pop(0)

    def _with_identity(self, response: LLMResponse) -> LLMResponse:
        response.provider = response.provider or self.name
        response.model = response.model or self.model
        return response

    def _usage(self, output_chars: int) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "input_tokens": 10 * self._call_index,
            "output_tokens": max(1, output_chars // 4),
        }
