"""Unit tests for core.stream_guard (AG-0.4)."""

from providers.types import LLMStreamChunk, ToolCall, ToolCallDelta
from core.stream_guard import guard_stream, sanitize_tool_calls, GuardedProvider


def _chunks(*items):
    return iter(items)


def test_guard_passes_content_through():
    c1 = LLMStreamChunk(content_delta="hello ")
    c2 = LLMStreamChunk(content_delta="world")
    out = list(guard_stream(_chunks(c1, c2)))
    assert "".join(c.content_delta for c in out) == "hello world"


def test_guard_consolidates_valid_tool_call():
    chunks = [
        LLMStreamChunk(tool_call_deltas=[
            ToolCallDelta(index=0, id="call_1", name="rag_search"),
            ToolCallDelta(index=0, arguments='{"q"'),
        ]),
        LLMStreamChunk(tool_call_deltas=[
            ToolCallDelta(index=0, arguments=': "x"}'),
        ]),
    ]
    out = list(guard_stream(_chunks(*chunks)))
    deltas = [d for c in out for d in c.tool_call_deltas]
    assert len(deltas) == 1
    assert deltas[0].name == "rag_search"
    assert deltas[0].id == "call_1"
    assert deltas[0].arguments == '{"q": "x"}'


def test_guard_recovers_nameless_tool_call_as_text():
    chunks = [
        LLMStreamChunk(tool_call_deltas=[
            ToolCallDelta(index=0, id="call_1", arguments='{"query": "hi"}'),
        ]),
    ]
    out = list(guard_stream(_chunks(*chunks)))
    deltas = [d for c in out for d in c.tool_call_deltas]
    assert deltas == []
    text = "".join(c.content_delta for c in out)
    assert "缺少工具名称" in text


def test_guard_drops_empty_fragments():
    chunks = [
        LLMStreamChunk(tool_call_deltas=[ToolCallDelta(index=0)]),
    ]
    out = list(guard_stream(_chunks(*chunks)))
    assert out == []


def test_guard_multiple_indices_are_isolated():
    chunks = [
        LLMStreamChunk(tool_call_deltas=[
            ToolCallDelta(index=0, name="a"),
            ToolCallDelta(index=1, name="b"),
        ]),
    ]
    out = list(guard_stream(_chunks(*chunks)))
    deltas = [d for c in out for d in c.tool_call_deltas]
    assert sorted(d.name for d in deltas) == ["a", "b"]


def test_sanitize_tool_calls_keeps_named_calls():
    calls = [ToolCall(id="c1", name="rag_search", arguments="{}")]
    valid, text = sanitize_tool_calls(calls, "hello")
    assert len(valid) == 1
    assert text == "hello"


def test_sanitize_tool_calls_recovers_nameless_calls():
    calls = [ToolCall(id="c1", name="", arguments='{"q": "x"}')]
    valid, text = sanitize_tool_calls(calls, "answer")
    assert valid == []
    assert "缺少工具名称" in text
    assert text.startswith("answer")


def test_sanitize_tool_calls_handles_none():
    valid, text = sanitize_tool_calls(None, "content")
    assert valid == []
    assert text == "content"


def test_guarded_provider_complete_sanitizes(monkeypatch):
    class FakeProvider:
        name = "fake"
        model = "m"

        def complete(self, messages, tools=None):
            from providers.types import LLMResponse
            return LLMResponse(
                content="answer",
                tool_calls=[ToolCall(id="c1", name="", arguments="{}")],
            )

        def complete_stream(self, messages, tools=None):
            yield LLMStreamChunk(content_delta="hi")

        def get_name(self):
            return "fake"

    guarded = GuardedProvider(FakeProvider())
    response = guarded.complete([{"role": "user", "content": "x"}])
    assert response.tool_calls == []
    assert "缺少工具名称" in response.content


def test_guarded_provider_stream_yields_sanitized_chunks():
    class FakeProvider:
        name = "fake"
        model = "m"

        def complete_stream(self, messages, tools=None):
            yield LLMStreamChunk(tool_call_deltas=[ToolCallDelta(index=0, name="rag_search")])

        def get_name(self):
            return "fake"

    guarded = GuardedProvider(FakeProvider())
    out = list(guarded.complete_stream([{"role": "user", "content": "x"}]))
    assert len(out) == 1
    assert out[0].tool_call_deltas[0].name == "rag_search"
