import json
import logging
import time
from collections.abc import Iterator
from typing import List

import httpx

from .base import LLMProvider
from .types import LLMResponse, LLMStreamChunk, ToolCall, ToolCallDelta

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    """Base provider for OpenAI-compatible APIs (Deepseek, OpenAI, etc.)."""

    def __init__(self, api_key: str, model: str,
                 base_url: str, provider_name: str,
                 temperature: float = 0.7, timeout: int = 60,
                 max_retries: int = 3):
        self.name = provider_name
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries

    def _convert_messages(self, messages: List[dict]) -> List[dict]:
        """Convert session messages to OpenAI API format."""
        raw = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                raw.append({"role": "system", "content": content})
            elif role == "user":
                raw.append({"role": "user", "content": content})
            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    formatted = []
                    for tc in tool_calls:
                        tc_id, name, args_str = self._parse_tool_call(tc)
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

    @staticmethod
    def _parse_tool_call(tc) -> tuple[str, str, str]:
        """Parse a tool call dict/object into (id, name, arguments_json)."""
        if isinstance(tc, dict):
            if "function" in tc:
                func = tc.get("function", {})
                name = func.get("name", "")
                args_str = func.get("arguments", "{}")
            else:
                name = tc.get("name", "")
                args_str = tc.get("args", "{}")
            tc_id = tc.get("id") or f"call_{name}"
        else:
            name = getattr(tc, "name", "") or ""
            args_str = getattr(tc, "args", "{}")
            tc_id = getattr(tc, "id", None) or f"call_{name}"
        # Normalize arguments to JSON string
        if not isinstance(args_str, str):
            args_str = json.dumps(args_str)
        return tc_id, name, args_str

    @staticmethod
    def _normalize_usage(data: dict) -> dict | None:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return None
        prompt_details = usage.get("prompt_tokens_details") or {}
        cached = usage.get("prompt_cache_hit_tokens")
        if cached is None:
            cached = prompt_details.get("cached_tokens")
        missed = usage.get("prompt_cache_miss_tokens")
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        cached_tokens = int(cached or 0) if cached is not None else None
        missed_tokens = int(missed or 0) if missed is not None else (
            max(0, prompt_tokens - cached_tokens) if cached_tokens is not None else None
        )
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        cost = usage.get("cost")
        if cost is None and isinstance(usage.get("cost_details"), dict):
            cost = usage["cost_details"].get("upstream_inference_cost")
        return {
            "input_tokens": prompt_tokens,
            "output_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "cache_read_tokens": cached_tokens,
            "cache_miss_tokens": missed_tokens,
            "reasoning_tokens": int(reasoning or 0) if reasoning is not None else None,
            "cache_reported": cached is not None or missed is not None,
            "cost_usd": float(cost) if cost is not None else None,
        }

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse OpenAI-format response JSON into LLMResponse."""
        choice = data["choices"][0]
        msg = choice["message"]
        content = msg.get("content", "") or ""
        raw_calls = msg.get("tool_calls", []) or []
        tool_calls = []
        for tc in raw_calls:
            func = tc.get("function", {})
            tool_calls.append(ToolCall(
                id=tc.get("id", ""),
                name=func.get("name", ""),
                arguments=func.get("arguments", "{}"),
            ))
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider=self.name,
            model=self.model,
            request_id=str(data.get("id") or ""),
            usage=self._normalize_usage(data),
        )

    def _build_payload(self, messages: List[dict], tools: List[dict] = None, stream: bool = False) -> dict:
        payload = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse_stream_chunk(data: dict) -> LLMStreamChunk:
        choice = data.get("choices", [{}])[0]
        delta = choice.get("delta") or {}
        content_delta = delta.get("content") or ""
        tool_call_deltas = []

        for raw in delta.get("tool_calls") or []:
            function = raw.get("function") or {}
            tool_call_deltas.append(ToolCallDelta(
                index=raw.get("index", 0),
                id=raw.get("id") or "",
                name=function.get("name") or "",
                arguments=function.get("arguments") or "",
            ))

        return LLMStreamChunk(
            content_delta=content_delta,
            tool_call_deltas=tool_call_deltas,
            usage=OpenAICompatibleProvider._normalize_usage(data),
            request_id=str(data.get("id") or ""),
        )

    def complete(self, messages: List[dict], tools: List[dict] = None) -> LLMResponse:
        payload = self._build_payload(messages, tools=tools)
        headers = self._headers()

        last_error = None
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                    response = client.post("/chat/completions", headers=headers, json=payload)

                    if response.status_code == 200:
                        return self._parse_response(response.json())

                    if response.status_code == 429 or response.status_code >= 500:
                        last_error = f"{self.name} API error: {response.status_code}"
                        logger.warning(f"[{self.name}] {last_error} — retry {attempt + 1}/{self.max_retries}")
                        time.sleep(2 ** attempt)
                        continue

                    raise Exception(f"{self.name} API error: {response.status_code} - {response.text}")

            except httpx.TimeoutException:
                last_error = f"{self.name} API timeout"
                logger.warning(f"[{self.name}] {last_error} — retry {attempt + 1}/{self.max_retries}")
                time.sleep(2 ** attempt)
            except httpx.ConnectError:
                last_error = f"{self.name} API connection error"
                logger.warning(f"[{self.name}] {last_error} — retry {attempt + 1}/{self.max_retries}")
                time.sleep(2 ** attempt)

        raise Exception(f"{self.name} API failed after {self.max_retries} retries: {last_error}")

    def complete_stream(self, messages: List[dict], tools: List[dict] = None) -> Iterator[LLMStreamChunk]:
        payload = self._build_payload(messages, tools=tools, stream=True)
        headers = self._headers()

        last_error = None
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                    with client.stream("POST", "/chat/completions", headers=headers, json=payload) as response:
                        if response.status_code == 200:
                            for line in response.iter_lines():
                                if isinstance(line, bytes):
                                    line = line.decode("utf-8", errors="replace")
                                line = line.strip()
                                if not line.startswith("data: "):
                                    continue
                                data = line[6:].strip()
                                if data == "[DONE]":
                                    return
                                if not data:
                                    continue
                                yield self._parse_stream_chunk(json.loads(data))
                            return

                        if response.status_code == 429 or response.status_code >= 500:
                            response.read()
                            last_error = f"{self.name} API error: {response.status_code}"
                            logger.warning(f"[{self.name}] {last_error} - retry {attempt + 1}/{self.max_retries}")
                            time.sleep(2 ** attempt)
                            continue

                        response.read()
                        raise Exception(f"{self.name} API error: {response.status_code} - {response.text}")

            except httpx.TimeoutException:
                last_error = f"{self.name} API timeout"
                logger.warning(f"[{self.name}] {last_error} - retry {attempt + 1}/{self.max_retries}")
                time.sleep(2 ** attempt)
            except httpx.ConnectError:
                last_error = f"{self.name} API connection error"
                logger.warning(f"[{self.name}] {last_error} - retry {attempt + 1}/{self.max_retries}")
                time.sleep(2 ** attempt)

        raise Exception(f"{self.name} API failed after {self.max_retries} retries: {last_error}")

    def get_name(self) -> str:
        return self.name
