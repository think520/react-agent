import json
import logging
from collections.abc import Iterator
from typing import List

from .openai_compat import OpenAICompatibleProvider
from .types import LLMResponse, LLMStreamChunk, ToolCall

logger = logging.getLogger(__name__)


class MiniMaxProvider(OpenAICompatibleProvider):
    """MiniMax provider with MiniMax-specific message conversion and parsing."""

    def __init__(
        self,
        api_key: str,
        model: str = "MiniMax-M2.7",
        base_url: str = "https://api.minimaxi.com/v1",
        temperature: float = 0.7,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider_name="minimax",
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )

    def _convert_messages(self, messages: List[dict]) -> List[dict]:
        """Convert session messages to MiniMax's OpenAI-compatible format.

        MiniMax only supports a single system message. All system messages
        are merged into one at the beginning.
        """
        # Merge all system messages into one
        system_parts = []
        non_system = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg.get("content", ""))
            else:
                non_system.append(msg)

        raw = []
        if system_parts:
            raw.append({"role": "system", "content": "\n\n".join(system_parts)})

        for msg in non_system:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "user":
                raw.append({"role": "user", "content": content})
            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    formatted = []
                    for tc in tool_calls:
                        tc_id, name, args_str = self._parse_tool_call(tc)
                        try:
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str
                            args_str = json.dumps(args)
                        except (json.JSONDecodeError, TypeError):
                            args_str = "{}"
                        formatted.append({
                            "id": tc_id,
                            "type": "function",
                            "function": {"name": name, "arguments": args_str},
                        })
                    raw.append({
                        "role": "assistant",
                        "content": content or "",
                        "tool_calls": formatted,
                    })
                else:
                    raw.append({"role": "assistant", "content": content or ""})
            elif role == "tool":
                raw.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": str(content),
                })
        return raw

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse MiniMax response and ignore tool calls when the model refused."""
        choice = data["choices"][0]
        response_msg = choice["message"]
        content = response_msg.get("content", "") or ""
        raw_calls = response_msg.get("tool_calls", []) or []

        refusal_indicators = [
            "\u4e0d\u80fd", "\u65e0\u6cd5", "\u62b1\u6b49", "\u5bf9\u4e0d\u8d77",
            "cannot", "unable", "sorry", "apologize", "apolog",
        ]
        if raw_calls and any(ind in content for ind in refusal_indicators):
            logger.info("[MiniMax] refusal detected with tool_calls; skipping tool execution")
            raw_calls = []

        tool_calls = []
        for tc in raw_calls:
            func = tc.get("function", {})
            tool_calls.append(ToolCall(
                id=tc.get("id", ""),
                name=func.get("name", ""),
                arguments=func.get("arguments", "{}"),
            ))
            logger.info("[MiniMax] tool_call id=%r name=%r", tc.get("id"), func.get("name"))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider=self.name,
            model=self.model,
            request_id=str(data.get("id") or ""),
            usage=self._normalize_usage(data),
        )

    def complete_stream(self, messages: List[dict], tools: List[dict] = None) -> Iterator[LLMStreamChunk]:
        """Hold tool deltas until refusal detection has seen the full response."""
        content = ""
        pending_tool_deltas = []
        last_request_id = ""
        for chunk in super().complete_stream(messages, tools):
            content += chunk.content_delta
            pending_tool_deltas.extend(chunk.tool_call_deltas)
            last_request_id = chunk.request_id or last_request_id
            yield LLMStreamChunk(
                content_delta=chunk.content_delta,
                usage=chunk.usage,
                request_id=chunk.request_id,
            )
        refusal_indicators = ("不能", "无法", "抱歉", "对不起", "cannot", "unable", "sorry", "apolog")
        if pending_tool_deltas and not any(item in content.casefold() for item in refusal_indicators):
            yield LLMStreamChunk(tool_call_deltas=pending_tool_deltas, request_id=last_request_id)
