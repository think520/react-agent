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
    assert events[-1]["type"] == "assistant_done"
    assert events[-1]["content"] == "hello"
    assert events[-1]["termination_reason"] == "final_answer"
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
    assert events[-1]["type"] == "assistant_done"
    assert events[-1]["content"] == "done"
    assert events[-1]["termination_reason"] == "final_answer"


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


def test_read_file_description_points_summary_tasks_to_delegate_doc_reader():
    read_file_schema = next(
        schema for schema in TOOL_SCHEMAS
        if schema.get("function", {}).get("name") == "read_file"
    )
    desc = read_file_schema["function"]["description"]
    assert "delegate_doc_reader" in desc
    assert "summar" in desc.lower()


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


# --- P2-1: termination_reason tests ---

def test_termination_reason_final_answer():
    session = Session.new("/test")
    llm = MockLLMProvider([LLMResponse(content="answer")])
    agent = AgentLoop(llm, session)

    events = list(agent.run_stream("question"))
    done = [e for e in events if e["type"] == "assistant_done"]

    assert len(done) == 1
    assert done[0]["termination_reason"] == "final_answer"


def test_termination_reason_max_iter(tmp_path):
    session = Session.new(str(tmp_path))
    llm = MockLLMProvider([
        _tool_response([{"name": "read_file", "args": {"path": "missing.txt"}}])
    ])
    agent = AgentLoop(llm, session)
    agent.max_iterations = 1

    events = list(agent.run_stream("loop"))
    done = [e for e in events if e["type"] == "assistant_done"]

    assert len(done) == 1
    assert done[0]["termination_reason"] == "max_iter"


def test_termination_reason_error():
    class BrokenProvider:
        def complete(self, messages, tools=None):
            raise RuntimeError("LLM exploded")
        def get_name(self):
            return "broken"

    session = Session.new("/test")
    agent = AgentLoop(BrokenProvider(), session)

    events = []
    try:
        for event in agent.run_stream("crash"):
            events.append(event)
    except RuntimeError:
        pass

    done = [e for e in events if e["type"] == "assistant_done"]
    assert len(done) == 1
    assert done[0]["termination_reason"] == "error"


# --- P2-2: TraceWriter tests ---

def test_trace_writer_creates_file(tmp_path):
    from core.trace import TraceWriter

    writer = TraceWriter("test-session-123", str(tmp_path))
    writer.write({"type": "tool_start", "tool_call_id": "c1", "tool_name": "read_file", "args": {"path": "x.txt"}})
    writer.write({"type": "assistant_done", "content": "hi", "termination_reason": "final_answer"})

    assert writer.path.endswith(".jsonl")
    assert (tmp_path / ".bobodan" / "traces").is_dir()

    import json
    from pathlib import Path
    lines = Path(writer.path).read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    r1 = json.loads(lines[0])
    assert r1["type"] == "tool_start"
    assert r1["tool_name"] == "read_file"
    assert r1["tool_call_id"] == "c1"
    r2 = json.loads(lines[1])
    assert r2["type"] == "assistant_done"
    assert r2["termination_reason"] == "final_answer"


def test_trace_writer_filters_non_traced_events(tmp_path):
    from core.trace import TraceWriter

    writer = TraceWriter("sess", str(tmp_path))
    writer.write({"type": "assistant_delta", "content": "chunk"})
    writer.write({"type": "tool_start", "tool_call_id": "c1", "tool_name": "x", "args": {}})
    writer.write({"type": "specialist_event", "event_type": "tool_start"})

    import json
    from pathlib import Path
    lines = Path(writer.path).read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "tool_start"


def test_trace_writer_redacts_secrets(tmp_path):
    from core.trace import TraceWriter
    import json

    writer = TraceWriter("sess", str(tmp_path))
    writer.write({
        "type": "tool_start",
        "tool_call_id": "c1",
        "tool_name": "http_request",
        "args": {"url": "https://api.example.com", "api_key": "sk-secret-123", "password": "hunter2"},
    })

    from pathlib import Path
    lines = Path(writer.path).read_text(encoding="utf-8").strip().split("\n")
    record = json.loads(lines[0])
    assert record["args"]["api_key"] == "***"
    assert record["args"]["password"] == "***"
    assert record["args"]["url"] == "https://api.example.com"


def test_trace_writer_truncates_long_content(tmp_path):
    from core.trace import TraceWriter, _MAX_CONTENT_LEN
    import json

    writer = TraceWriter("sess", str(tmp_path))
    long_text = "x" * 1000
    writer.write({"type": "tool_end", "tool_call_id": "c1", "tool_name": "x", "ok": True,
                  "content": long_text, "elapsed": 0.1})

    from pathlib import Path
    lines = Path(writer.path).read_text(encoding="utf-8").strip().split("\n")
    record = json.loads(lines[0])
    assert len(record["content"]) == _MAX_CONTENT_LEN
    assert record["content"].endswith("...")


def test_trace_writer_tool_end_event(tmp_path):
    from core.trace import TraceWriter
    import json

    writer = TraceWriter("sess", str(tmp_path))
    writer.write({"type": "tool_end", "tool_call_id": "c1", "tool_name": "read_file",
                  "ok": True, "content": "read 100 chars", "elapsed": 0.5,
                  "result_summary": "→ /some/path"})

    from pathlib import Path
    lines = Path(writer.path).read_text(encoding="utf-8").strip().split("\n")
    record = json.loads(lines[0])
    assert record["type"] == "tool_end"
    assert record["ok"] is True
    assert record["elapsed"] == 0.5
    assert record["result_summary"] == "→ /some/path"


def test_trace_writer_error_event(tmp_path):
    from core.trace import TraceWriter
    import json

    writer = TraceWriter("sess", str(tmp_path))
    writer.write({"type": "error", "error": "connection timeout"})

    from pathlib import Path
    lines = Path(writer.path).read_text(encoding="utf-8").strip().split("\n")
    record = json.loads(lines[0])
    assert record["type"] == "error"
    assert record["error"] == "connection timeout"


def test_agent_loop_writes_trace(tmp_path):
    from core.trace import TraceWriter

    session = Session.new(str(tmp_path))
    llm = MockLLMProvider([LLMResponse(content="done")])
    writer = TraceWriter("test-sess", str(tmp_path))
    agent = AgentLoop(llm, session, trace_writer=writer)

    list(agent.run_stream("hi"))

    import json
    from pathlib import Path
    lines = Path(writer.path).read_text(encoding="utf-8").strip().split("\n")
    types = [json.loads(l)["type"] for l in lines]
    assert "assistant_done" in types


def test_agent_loop_trace_includes_tool_events(tmp_path):
    from core.trace import TraceWriter
    import json

    (tmp_path / "a.txt").write_text("content", encoding="utf-8")
    session = Session.new(str(tmp_path))
    llm = MockLLMProvider([
        _tool_response([{"name": "read_file", "args": {"path": "a.txt"}}]),
        LLMResponse(content="read done"),
    ])
    writer = TraceWriter("test-sess", str(tmp_path))
    agent = AgentLoop(llm, session, trace_writer=writer)

    list(agent.run_stream("read"))

    from pathlib import Path
    lines = Path(writer.path).read_text(encoding="utf-8").strip().split("\n")
    types = [json.loads(l)["type"] for l in lines]
    assert "tool_start" in types
    assert "tool_end" in types
    assert "assistant_done" in types


def test_agent_loop_no_trace_when_none():
    session = Session.new("/test")
    llm = MockLLMProvider([LLMResponse(content="ok")])
    agent = AgentLoop(llm, session, trace_writer=None)

    events = list(agent.run_stream("hi"))
    done = [e for e in events if e["type"] == "assistant_done"]
    assert len(done) == 1
    assert done[0]["termination_reason"] == "final_answer"


# --- Trace reading tests ---

def test_list_traces_empty(tmp_path):
    from core.trace import list_traces
    assert list_traces(str(tmp_path)) == []


def test_list_traces_returns_sorted_entries(tmp_path):
    import time
    from core.trace import list_traces, TraceWriter
    # Create two trace files with a small gap to ensure distinct mtimes
    w1 = TraceWriter("sess-aaa", str(tmp_path))
    w1.write({"type": "assistant_done", "content": "a", "termination_reason": "final_answer"})
    time.sleep(0.05)
    w2 = TraceWriter("sess-bbb", str(tmp_path))
    w2.write({"type": "assistant_done", "content": "b", "termination_reason": "final_answer"})

    traces = list_traces(str(tmp_path))
    assert len(traces) == 2
    ids = [t["session_id"] for t in traces]
    assert "sess-aaa" in ids
    assert "sess-bbb" in ids


def test_list_traces_respects_limit(tmp_path):
    from core.trace import list_traces, TraceWriter
    for i in range(5):
        w = TraceWriter(f"sess-{i}", str(tmp_path))
        w.write({"type": "assistant_done", "content": "", "termination_reason": "final_answer"})

    assert len(list_traces(str(tmp_path), limit=3)) == 3


def test_read_trace(tmp_path):
    from core.trace import TraceWriter, read_trace
    import json

    writer = TraceWriter("sess", str(tmp_path))
    writer.write({"type": "tool_start", "tool_call_id": "c1", "tool_name": "read_file", "args": {}})
    writer.write({"type": "tool_end", "tool_call_id": "c1", "tool_name": "read_file", "ok": True, "content": "ok", "elapsed": 0.1})
    writer.write({"type": "assistant_done", "content": "done", "termination_reason": "final_answer"})

    events = read_trace(writer.path)
    assert len(events) == 3
    assert events[0]["type"] == "tool_start"
    assert events[1]["type"] == "tool_end"
    assert events[2]["type"] == "assistant_done"


def test_read_trace_skips_blank_lines(tmp_path):
    from core.trace import read_trace
    from pathlib import Path

    path = tmp_path / "bad.jsonl"
    Path(path).write_text('{"type":"tool_start","tool_call_id":"c1","tool_name":"x","args":{}}\n\n{"type":"assistant_done","content":"","termination_reason":"final_answer"}\n', encoding="utf-8")

    events = read_trace(str(path))
    assert len(events) == 2


def test_summarize_trace(tmp_path):
    from core.trace import TraceWriter, read_trace, summarize_trace

    writer = TraceWriter("sess", str(tmp_path))
    writer.write({"type": "tool_start", "tool_call_id": "c1", "tool_name": "read_file", "args": {}})
    writer.write({"type": "tool_end", "tool_call_id": "c1", "tool_name": "read_file", "ok": True, "content": "ok", "elapsed": 0.5})
    writer.write({"type": "tool_start", "tool_call_id": "c2", "tool_name": "write_file", "args": {}})
    writer.write({"type": "tool_end", "tool_call_id": "c2", "tool_name": "write_file", "ok": False, "content": "err", "elapsed": 0.1})
    writer.write({"type": "assistant_done", "content": "done", "termination_reason": "final_answer"})

    events = read_trace(writer.path)
    s = summarize_trace(events)

    assert s["tool_count"] == 2
    assert s["tools_ok"] == 1
    assert s["tools_fail"] == 1
    assert s["termination_reason"] == "final_answer"
    assert len(s["tool_details"]) == 2
    assert s["tool_details"][0]["tool_name"] == "read_file"
    assert s["tool_details"][0]["ok"] is True
    assert s["tool_details"][1]["tool_name"] == "write_file"
    assert s["tool_details"][1]["ok"] is False


def test_summarize_trace_max_iter(tmp_path):
    from core.trace import TraceWriter, read_trace, summarize_trace

    writer = TraceWriter("sess", str(tmp_path))
    writer.write({"type": "assistant_done", "content": "loop", "termination_reason": "max_iter"})

    events = read_trace(writer.path)
    s = summarize_trace(events)

    assert s["tool_count"] == 0
    assert s["termination_reason"] == "max_iter"


def test_summarize_trace_error(tmp_path):
    from core.trace import TraceWriter, read_trace, summarize_trace

    writer = TraceWriter("sess", str(tmp_path))
    writer.write({"type": "error", "error": "connection timeout"})

    events = read_trace(writer.path)
    s = summarize_trace(events)

    assert s["tool_count"] == 1
    assert s["tools_fail"] == 1
    assert s["tool_details"][0]["tool_name"] == "(error)"
