import pytest
from providers.base import LLMProvider
from providers.types import LLMResponse, ToolCall
from providers.openai_compat import OpenAICompatibleProvider
from providers.minimax import MiniMaxProvider


class MockProvider:
    def __init__(self):
        self.name = "mock"

    def complete(self, messages: list[dict], tools: list[dict] = None) -> LLMResponse:
        return LLMResponse(content="mock response")

    def get_name(self) -> str:
        return self.name


def test_llm_provider_protocol():
    provider = MockProvider()
    assert isinstance(provider, LLMProvider)
    result = provider.complete([])
    assert isinstance(result, LLMResponse)
    assert result.content == "mock response"
    assert result.tool_calls == []
    assert provider.get_name() == "mock"


def test_llm_provider_accepts_tools():
    provider = MockProvider()
    result = provider.complete([], tools=[{"type": "function", "function": {"name": "test"}}])
    assert result.content == "mock response"


def test_tool_call_to_dict():
    tc = ToolCall(id="call_123", name="read_file", arguments='{"path": "test.txt"}')
    d = tc.to_dict()
    assert d == {
        "id": "call_123",
        "function": {
            "name": "read_file",
            "arguments": '{"path": "test.txt"}',
        },
    }


def test_llm_response_defaults():
    resp = LLMResponse()
    assert resp.content == ""
    assert resp.tool_calls == []


def test_llm_response_with_tool_calls():
    tc = ToolCall(id="c1", name="write_file", arguments='{"path":"a.txt","content":"x"}')
    resp = LLMResponse(content="", tool_calls=[tc])
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "write_file"


def test_openai_compat_parse_response():
    provider = OpenAICompatibleProvider(
        api_key="test", model="test", base_url="http://localhost", provider_name="test",
    )
    data = {
        "choices": [{
            "message": {
                "content": "hello",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'},
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "write_file", "arguments": '{"path":"b.txt","content":"x"}'},
                    },
                ],
            },
        }],
    }
    resp = provider._parse_response(data)
    assert resp.content == "hello"
    assert len(resp.tool_calls) == 2
    assert resp.tool_calls[0].id == "call_1"
    assert resp.tool_calls[0].name == "read_file"
    assert resp.tool_calls[1].id == "call_2"
    assert resp.tool_calls[1].name == "write_file"


def test_openai_compat_parse_response_no_tools():
    provider = OpenAICompatibleProvider(
        api_key="test", model="test", base_url="http://localhost", provider_name="test",
    )
    data = {
        "choices": [{
            "message": {
                "content": "just text",
                "tool_calls": None,
            },
        }],
    }
    resp = provider._parse_response(data)
    assert resp.content == "just text"
    assert resp.tool_calls == []


def test_openai_compat_parse_stream_chunk_tool_delta():
    data = {
        "choices": [{
            "delta": {
                "content": "",
                "tool_calls": [{
                    "index": 0,
                    "id": "call_1",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"a',
                    },
                }],
            },
        }],
    }

    chunk = OpenAICompatibleProvider._parse_stream_chunk(data)

    assert chunk.content_delta == ""
    assert len(chunk.tool_call_deltas) == 1
    assert chunk.tool_call_deltas[0].index == 0
    assert chunk.tool_call_deltas[0].id == "call_1"
    assert chunk.tool_call_deltas[0].name == "read_file"
    assert chunk.tool_call_deltas[0].arguments == '{"path":"a'


def test_openai_compat_convert_messages():
    provider = OpenAICompatibleProvider(
        api_key="test", model="test", base_url="http://localhost", provider_name="test",
    )
    messages = [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'}},
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "file content"},
        {"role": "assistant", "content": "I read the file"},
    ]
    converted = provider._convert_messages(messages)
    assert len(converted) == 5
    assert converted[0] == {"role": "system", "content": "you are helpful"}
    assert converted[1] == {"role": "user", "content": "hello"}
    assert converted[2]["role"] == "assistant"
    assert len(converted[2]["tool_calls"]) == 1
    assert converted[3]["role"] == "tool"
    assert converted[3]["tool_call_id"] == "c1"
    assert converted[4] == {"role": "assistant", "content": "I read the file"}


def test_openai_compat_multi_tool_calls():
    """OpenAICompatibleProvider correctly handles multiple tool calls in one message."""
    provider = OpenAICompatibleProvider(
        api_key="test", model="test", base_url="http://localhost", provider_name="test",
    )
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'}},
                {"id": "c2", "function": {"name": "write_file", "arguments": '{"path":"b.txt","content":"x"}'}},
            ],
        },
    ]
    converted = provider._convert_messages(messages)
    assert len(converted[0]["tool_calls"]) == 2
    assert converted[0]["tool_calls"][0]["id"] == "c1"
    assert converted[0]["tool_calls"][1]["id"] == "c2"


def test_minimax_convert_messages_merges_system():
    provider = MiniMaxProvider(
        api_key="test",
        model="MiniMax-M2.7",
        base_url="http://localhost",
    )
    messages = [
        {"role": "system", "content": "you are bobodan"},
        {"role": "system", "content": "skills prompt"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "tool", "tool_call_id": "c1", "content": "result"},
    ]

    converted = provider._convert_messages(messages)

    # System messages merged into one
    assert converted[0]["role"] == "system"
    assert "you are bobodan" in converted[0]["content"]
    assert "skills prompt" in converted[0]["content"]
    # No name fields on any message
    for msg in converted:
        assert "name" not in msg
