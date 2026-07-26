import httpx
import pytest
from providers.base import LLMProvider
from providers.errors import ProviderConfigError, ProviderTimeout
from providers.factory import ProviderFactory
from providers.types import LLMResponse, LLMStreamChunk, ToolCall
from providers.openai_compat import OpenAICompatibleProvider
from providers.minimax import MiniMaxProvider


class MockProvider:
    def __init__(self):
        self.name = "mock"
        self.model = "mock-model"

    def complete(self, messages: list[dict], tools: list[dict] = None) -> LLMResponse:
        return LLMResponse(content="mock response")

    def get_name(self) -> str:
        return self.name

    def complete_stream(self, messages: list[dict], tools: list[dict] = None):
        yield LLMStreamChunk(content_delta="mock response")


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


def test_openai_compat_normalizes_deepseek_and_openai_cache_usage():
    provider = OpenAICompatibleProvider(
        api_key="test", model="test-model", base_url="http://localhost", provider_name="deepseek",
    )
    deepseek = provider._parse_response({
        "id": "req-1",
        "choices": [{"message": {"content": "ok"}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
        },
    })
    assert deepseek.provider == "deepseek"
    assert deepseek.model == "test-model"
    assert deepseek.request_id == "req-1"
    assert deepseek.usage["cache_read_tokens"] == 80
    assert deepseek.usage["cache_miss_tokens"] == 20

    openai = provider._normalize_usage({"usage": {
        "prompt_tokens": 50,
        "completion_tokens": 10,
        "prompt_tokens_details": {"cached_tokens": 30},
        "cost": 0.0012,
    }})
    assert openai["cache_read_tokens"] == 30
    assert openai["cache_miss_tokens"] == 20
    assert openai["cost_usd"] == 0.0012


def test_openai_compat_marks_unreported_cache_as_unknown():
    usage = OpenAICompatibleProvider._normalize_usage({"usage": {
        "prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60,
    }})
    assert usage["cache_reported"] is False
    assert usage["cache_read_tokens"] is None


def test_openai_compat_parse_stream_chunk_tool_delta():
    data = {
        "id": "stream-1",
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
    assert chunk.request_id == "stream-1"


def test_openai_compat_requests_stream_usage():
    provider = OpenAICompatibleProvider(
        api_key="test", model="test", base_url="http://localhost", provider_name="test",
    )

    payload = provider._build_payload([{"role": "user", "content": "hi"}], stream=True)

    assert payload["stream_options"] == {"include_usage": True}


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


def test_openai_compat_timeout_raises_typed_error(monkeypatch):
    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("providers.openai_compat.httpx.Client", Client)
    monkeypatch.setattr("providers.openai_compat.time.sleep", lambda _seconds: None)
    provider = OpenAICompatibleProvider(
        api_key="test", model="test", base_url="http://localhost",
        provider_name="test", max_retries=1,
    )

    with pytest.raises(ProviderTimeout):
        provider.complete([{"role": "user", "content": "hi"}])


def test_provider_factory_uses_registry_and_typed_config_errors(monkeypatch):
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret")
    provider = ProviderFactory.create(
        {"type": "openai_compatible", "api_key_env": "TEST_PROVIDER_KEY", "model": "custom"},
        {"temperature": 0.2},
    )
    assert provider.name == "openai_compatible"
    assert provider.model == "custom"
    with pytest.raises(ProviderConfigError):
        ProviderFactory.create({"type": "unknown", "api_key_env": "TEST_PROVIDER_KEY"}, {})


def test_minimax_stream_refusal_drops_buffered_tool_calls(monkeypatch):
    def stream(_self, _messages, _tools=None):
        yield LLMStreamChunk(tool_call_deltas=[{"index": 0}], request_id="r1")
        yield LLMStreamChunk(content_delta="抱歉，我无法执行这个操作。", request_id="r1")

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_stream", stream)
    chunks = list(MiniMaxProvider(api_key="test").complete_stream([]))
    assert "".join(chunk.content_delta for chunk in chunks) == "抱歉，我无法执行这个操作。"
    assert not any(chunk.tool_call_deltas for chunk in chunks)


def test_minimax_stream_emits_buffered_tool_calls_when_not_refused(monkeypatch):
    delta = {"index": 0, "id": "call-1"}

    def stream(_self, _messages, _tools=None):
        yield LLMStreamChunk(tool_call_deltas=[delta], request_id="r1")
        yield LLMStreamChunk(content_delta="我来查询资料。", request_id="r1")

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_stream", stream)
    chunks = list(MiniMaxProvider(api_key="test").complete_stream([]))
    assert chunks[-1].tool_call_deltas == [delta]
