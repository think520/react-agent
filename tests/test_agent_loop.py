from core.agent_loop import AgentLoop, LEGACY_BASE_SYSTEM_PROMPT
from core.session import Session
from providers.types import LLMResponse, LLMStreamChunk, ToolCall, ToolCallDelta
from tools.base import TOOL_REGISTRY, TOOL_SCHEMAS, ToolResult, register_tool


class MockLLMProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def complete(self, messages, tools=None):
        response = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return response

    def get_name(self):
        return "mock"


class StreamingLLMProvider:
    def __init__(self, chunk_groups):
        self.chunk_groups = list(chunk_groups)
        self.call_count = 0

    def complete_stream(self, messages, tools=None):
        chunks = self.chunk_groups[min(self.call_count, len(self.chunk_groups) - 1)]
        self.call_count += 1
        yield from chunks

    def complete(self, messages, tools=None):
        raise AssertionError("streaming provider should use complete_stream")

    def get_name(self):
        return "streaming"


def _tool_response(tool_calls_data, content=""):
    """Build an LLMResponse with tool calls."""
    return LLMResponse(
        content=content,
        tool_calls=[
            ToolCall(
                id=tc.get("id", f"call_{tc['name']}"),
                name=tc["name"],
                arguments=tc["args"],
            )
            for tc in tool_calls_data
        ],
    )


def test_agent_loop_plain_text_response():
    session = Session.new("/test")
    llm = MockLLMProvider([LLMResponse(content="direct response")])
    agent = AgentLoop(llm, session)

    result = agent.run("hello")

    assert result == "direct response"
    assert session.messages[-1]["content"] == "direct response"


def test_agent_loop_removes_legacy_base_system_prompt():
    session = Session.new("/test")
    session.add_message("system", LEGACY_BASE_SYSTEM_PROMPT)
    llm = MockLLMProvider([LLMResponse(content="direct response")])
    agent = AgentLoop(llm, session)

    agent.run("hello")

    system_messages = [m for m in session.messages if m["role"] == "system"]
    assert all(m["content"] != LEGACY_BASE_SYSTEM_PROMPT for m in system_messages)


def test_agent_loop_streams_text_events():
    session = Session.new("/test")
    llm = StreamingLLMProvider([
        [
            LLMStreamChunk(content_delta="hel"),
            LLMStreamChunk(content_delta="lo"),
        ]
    ])
    agent = AgentLoop(llm, session)

    events = list(agent.run_stream("hi"))

    assert [event["content"] for event in events if event["type"] == "assistant_delta"] == ["hel", "lo"]
    assert events[-1] == {"type": "assistant_done", "content": "hello"}
    assert session.messages[-1]["content"] == "hello"


def test_agent_loop_streams_tool_events_and_accumulates_arguments(tmp_path):
    session = Session.new(str(tmp_path))
    llm = StreamingLLMProvider([
        [
            LLMStreamChunk(tool_call_deltas=[
                ToolCallDelta(index=0, id="call_1", name="write_file", arguments='{"path":"'),
            ]),
            LLMStreamChunk(tool_call_deltas=[
                ToolCallDelta(index=0, arguments='stream.txt","content":"ok"}'),
            ]),
        ],
        [
            LLMStreamChunk(content_delta="done"),
        ],
    ])
    agent = AgentLoop(llm, session)

    events = list(agent.run_stream("write"))

    assert (tmp_path / "stream.txt").read_text(encoding="utf-8") == "ok"
    assert any(event["type"] == "tool_start" and event["tool_name"] == "write_file" for event in events)
    assert any(event["type"] == "tool_end" and event["ok"] for event in events)
    assert events[-1] == {"type": "assistant_done", "content": "done"}


def test_agent_loop_tool_call_then_text(tmp_path):
    session = Session.new(str(tmp_path))
    llm = MockLLMProvider([
        _tool_response([
            {"name": "write_file", "args": {"path": "test.txt", "content": "hello world"}}
        ]),
        LLMResponse(content="done"),
    ])
    agent = AgentLoop(llm, session)

    result = agent.run("write file")

    assert result == "done"
    assert (tmp_path / "test.txt").read_text(encoding="utf-8") == "hello world"


def test_agent_loop_yields_specialist_display_events_without_session_pollution(tmp_path):
    def delegate_fake():
        return ToolResult(
            ok=True,
            content="specialist summary",
            data={
                "display_events": [
                    {"type": "tool_start", "tool_name": "read_file", "args": {"path": "x.md"}},
                    {"type": "tool_end", "tool_name": "read_file", "ok": True, "content": "read 10 chars"},
                ]
            },
        )

    TOOL_REGISTRY.pop("delegate_fake", None)
    TOOL_SCHEMAS[:] = [
        schema for schema in TOOL_SCHEMAS
        if schema.get("function", {}).get("name") != "delegate_fake"
    ]
    register_tool(
        "delegate_fake",
        "fake delegate",
        {"type": "object", "properties": {}},
        delegate_fake,
    )
    try:
        session = Session.new(str(tmp_path))
        llm = MockLLMProvider([
            _tool_response([
                {"name": "delegate_fake", "args": {}}
            ]),
            LLMResponse(content="done"),
        ])
        agent = AgentLoop(llm, session)

        events = list(agent.run_stream("delegate"))

        specialist_events = [event for event in events if event["type"] == "specialist_event"]
        assert [event["tool_name"] for event in specialist_events] == ["read_file", "read_file"]
        tool_messages = [m for m in session.messages if m["role"] == "tool"]
        assert tool_messages == [{
            "role": "tool",
            "tool_call_id": "call_delegate_fake",
            "content": "specialist summary",
        }]
    finally:
        TOOL_REGISTRY.pop("delegate_fake", None)
        TOOL_SCHEMAS[:] = [
            schema for schema in TOOL_SCHEMAS
            if schema.get("function", {}).get("name") != "delegate_fake"
        ]


def test_agent_loop_multi_tool_calls(tmp_path):
    """Multiple tool calls in one response are all executed."""
    (tmp_path / "a.txt").write_text("existing", encoding="utf-8")
    session = Session.new(str(tmp_path))
    llm = MockLLMProvider([
        _tool_response([
            {"name": "read_file", "args": {"path": "a.txt"}},
            {"name": "write_file", "args": {"path": "b.txt", "content": "new"}},
        ]),
        LLMResponse(content="both done"),
    ])
    agent = AgentLoop(llm, session)

    result = agent.run("read and write")

    assert result == "both done"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "new"


def test_agent_loop_message_order(tmp_path):
    """Session messages follow: user -> assistant(tool_calls) -> tool -> assistant."""
    session = Session.new(str(tmp_path))
    llm = MockLLMProvider([
        _tool_response([
            {"name": "write_file", "args": {"path": "x.txt", "content": "hi"}}
        ]),
        LLMResponse(content="ok"),
    ])
    agent = AgentLoop(llm, session)
    agent.run("write")

    non_system_messages = [m for m in session.messages if m["role"] != "system"]
    roles = [m["role"] for m in non_system_messages]
    # user -> assistant(tool_calls) -> tool -> assistant
    assert roles == ["user", "assistant", "tool", "assistant"]
    # assistant(tool_calls) must come before tool
    assert "tool_calls" in non_system_messages[1]
    assert non_system_messages[2]["role"] == "tool"


def test_agent_loop_updates_session_cwd_on_change_dir(tmp_path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    session = Session.new(str(tmp_path))
    original_workspace = session.workspace_root
    llm = MockLLMProvider([
        _tool_response([
            {"name": "change_dir", "args": {"path": str(subdir.name)}}
        ]),
        LLMResponse(content="changed"),
    ])
    agent = AgentLoop(llm, session)

    result = agent.run("go to subdir")

    assert result == "changed"
    assert session.cwd == str(subdir.resolve())
    assert session.workspace_root == original_workspace  # workspace_root unchanged


def test_agent_loop_stops_after_max_iterations(tmp_path):
    session = Session.new(str(tmp_path))
    llm = MockLLMProvider([
        _tool_response([
            {"name": "read_file", "args": {"path": "missing.txt"}}
        ])
    ])
    agent = AgentLoop(llm, session)
    agent.max_iterations = 2

    result = agent.run("loop forever")

    assert result == "Agent stopped after too many tool iterations."
