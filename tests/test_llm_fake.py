"""Tests for the canonical scripted LLM provider (tests/llm_fake.py).

The fake is infrastructure every other test relies on, so it gets its own
contract tests: streaming chunking, tool-call turns, error injection and
request recording.
"""

import json

import pytest

from providers.errors import ProviderError
from tests.llm_fake import ScriptedProvider


def test_text_turn_streams_in_chunks_with_usage(scripted_provider):
    scripted_provider.queue("一二三四五六七八九十")
    chunks = list(scripted_provider.complete_stream([{"role": "user", "content": "hi"}]))
    body = "".join(chunk.content_delta for chunk in chunks)
    assert body == "一二三四五六七八九十"
    # Chunked emission, not one blob.
    assert len([c for c in chunks if c.content_delta]) > 1
    # Final chunk carries usage for downstream accounting.
    assert chunks[-1].usage["output_tokens"] >= 1
    assert chunks[-1].request_id == chunks[0].request_id


def test_complete_returns_text_and_records_request(scripted_provider):
    scripted_provider.queue("回答内容")
    tools = [{"type": "function", "function": {"name": "rag_search"}}]
    response = scripted_provider.complete([{"role": "user", "content": "问"}], tools=tools)
    assert response.content == "回答内容"
    assert response.provider == "scripted"
    assert response.usage["input_tokens"] > 0
    assert scripted_provider.call_count == 1
    assert scripted_provider.last_messages()[0]["content"] == "问"
    assert scripted_provider.requests[0]["tools"] == tools


def test_tool_turn_complete_and_stream_shapes(scripted_provider):
    scripted_provider.queue({"tool": "rag_search", "args": {"query": "Dijkstra"}, "content": "先查资料"})
    response = scripted_provider.complete([])
    assert response.tool_calls[0].name == "rag_search"
    assert json.loads(response.tool_calls[0].arguments)["query"] == "Dijkstra"
    assert response.content == "先查资料"

    scripted_provider.queue({"tool": "kb_status", "args": {}})
    chunks = list(scripted_provider.complete_stream([]))
    deltas = [d for chunk in chunks for d in chunk.tool_call_deltas]
    assert deltas and deltas[0].name == "kb_status"


def test_error_injection_and_exhaustion(scripted_provider):
    scripted_provider.queue(ProviderError("boom"), "ok")
    with pytest.raises(ProviderError, match="boom"):
        scripted_provider.complete([])
    # The failed call still counted as a request.
    assert scripted_provider.call_count == 1
    assert scripted_provider.complete([]).content == "ok"

    exhausted = ScriptedProvider()
    with pytest.raises(ProviderError, match="ran out of turns"):
        exhausted.complete([])


def test_llm_response_turn_returned_verbatim_with_identity_fill(scripted_provider):
    from providers.types import LLMResponse

    scripted_provider.queue(LLMResponse(content="canned", provider="", model=""))
    response = scripted_provider.complete([])
    assert response.content == "canned"
    assert response.provider == "scripted"
    assert response.model == "scripted-model"
