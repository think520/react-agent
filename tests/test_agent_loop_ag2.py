"""Tests for AG-2 loop enhancements: hooks, allowlist gate, dedup, parallelism."""

import time

import pytest

from core.agent_loop import AgentLoop, READ_ONLY_TOOLS
from core.hooks import (
    AFTER_TOOL,
    AFTER_TURN,
    BEFORE_TOOL,
    BEFORE_TURN,
    block,
    clear_hooks,
    register_hook,
)
from core.session import Session
from providers.types import LLMResponse, ToolCall
from tools.base import TOOL_REGISTRY, ToolResult


@pytest.fixture(autouse=True)
def _clean_hooks():
    clear_hooks()
    yield
    clear_hooks()


def _tool_response(tool_calls_data, content=""):
    return LLMResponse(
        content=content,
        tool_calls=[
            ToolCall(id=tc.get("id", f"call_{tc['name']}"), name=tc["name"], arguments=tc["args"])
            for tc in tool_calls_data
        ],
    )


class MockLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def complete(self, messages, tools=None):
        response = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return response

    def get_name(self):
        return "mock"


def test_before_turn_hook_injects_and_is_cleaned_up():
    register_hook(BEFORE_TURN, lambda session, user_input: "<!-- injected -->recall: " + user_input)

    captured = []

    class CapturingLLM(MockLLM):
        def complete(self, messages, tools=None):
            captured.extend(dict(m) for m in messages)
            return LLMResponse(content="done")

    session = Session.new("/test")
    agent = AgentLoop(CapturingLLM([LLMResponse(content="done")]), session)

    assert agent.run("hello") == "done"
    assert any("recall: hello" in m.get("content", "") for m in captured)
    # The injection must not persist in the session.
    assert all("recall:" not in m.get("content", "") for m in session.messages)


def test_before_tool_hook_blocks_tool(tmp_path):
    register_hook(BEFORE_TOOL, lambda tool_name, args, session: block("denied by policy") if tool_name == "write_file" else None)

    session = Session.new(str(tmp_path))
    llm = MockLLM([
        _tool_response([{"name": "write_file", "args": {"path": "x.txt", "content": "no"}}]),
        LLMResponse(content="done"),
    ])
    agent = AgentLoop(llm, session)
    events = list(agent.run_stream("write"))

    assert not (tmp_path / "x.txt").exists()
    tool_end = next(e for e in events if e["type"] == "tool_end")
    assert tool_end["ok"] is False
    assert "denied by policy" in tool_end["content"]


def test_before_tool_hook_terminate_stops_turn(tmp_path):
    register_hook(BEFORE_TOOL, lambda tool_name, args, session: block("halt", terminate=True) if tool_name == "write_file" else None)

    session = Session.new(str(tmp_path))
    llm = MockLLM([
        _tool_response([{"name": "write_file", "args": {"path": "x.txt", "content": "no"}}]),
        LLMResponse(content="should not appear"),
    ])
    agent = AgentLoop(llm, session)
    events = list(agent.run_stream("write"))

    done = [e for e in events if e["type"] == "assistant_done"]
    assert done and done[-1]["content"] == "本轮操作被安全策略终止。"
    assert llm.call_count == 1  # terminated before the next completion


def test_after_tool_hook_replaces_result(tmp_path):
    register_hook(AFTER_TOOL, lambda tool_name, args, result, session: ToolResult(ok=True, content="sanitized") if tool_name == "read_file" else None)

    (tmp_path / "a.txt").write_text("content", encoding="utf-8")
    session = Session.new(str(tmp_path))
    llm = MockLLM([
        _tool_response([{"name": "read_file", "args": {"path": "a.txt"}}]),
        LLMResponse(content="done"),
    ])
    agent = AgentLoop(llm, session)
    events = list(agent.run_stream("read"))

    tool_end = next(e for e in events if e["type"] == "tool_end")
    assert tool_end["content"] == "sanitized"


def test_after_turn_hook_runs():
    seen = []
    register_hook(AFTER_TURN, lambda session, user_input, final_response, usage_records: seen.append(final_response))

    session = Session.new("/test")
    agent = AgentLoop(MockLLM([LLMResponse(content="final")]), session)
    agent.run("hi")

    assert seen == ["final"]


def test_read_only_tool_dedup(monkeypatch, tmp_path):
    calls = []

    def fake_rag(query, workspace="."):
        calls.append(query)
        return ToolResult(ok=True, content="result", data={"results": [{"text": "x"}], "hit_count": 1})

    monkeypatch.setitem(TOOL_REGISTRY, "rag_search", fake_rag)
    session = Session.new(str(tmp_path))
    llm = MockLLM([
        _tool_response([
            {"name": "rag_search", "args": {"query": "same"}},
            {"name": "rag_search", "args": {"query": "same"}},
        ]),
        LLMResponse(content="done"),
    ])
    agent = AgentLoop(llm, session)
    agent.run("search")

    # Same name + same args executed only once (AG-2.4).
    assert calls == ["same"]


def test_read_only_parallel_correct_results_and_event_order(monkeypatch, tmp_path):
    """Multiple read-only tools return correct results with ordered events."""
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "rag_search",
        lambda query, workspace=".": ToolResult(ok=True, content=f"r:{query}", data={"results": [{"text": query}], "hit_count": 1}),
    )
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "concept_map_query",
        lambda operation="query", query=None, concept=None, workspace=".": ToolResult(ok=True, content=f"c:{operation}", data={"operation": operation}),
    )

    session = Session.new(str(tmp_path))
    llm = MockLLM([
        _tool_response([
            {"name": "rag_search", "args": {"query": "q1"}},
            {"name": "concept_map_query", "args": {"operation": "search", "query": "q2"}},
        ]),
        LLMResponse(content="done"),
    ])
    agent = AgentLoop(llm, session)
    events = list(agent.run_stream("multi"))

    tool_starts = [e["tool_name"] for e in events if e["type"] == "tool_start"]
    tool_ends = [e for e in events if e["type"] == "tool_end"]
    assert tool_starts == ["rag_search", "concept_map_query"]
    assert [e["tool_name"] for e in tool_ends] == ["rag_search", "concept_map_query"]
    assert all(e["ok"] for e in tool_ends)


def test_read_only_tool_set_contains_expected_names():
    assert {"rag_search", "concept_map_query", "concept_map_status", "knowledge_status"} <= READ_ONLY_TOOLS


def test_write_tool_not_deduped(tmp_path):
    """Write tools are never de-duplicated and always re-execute."""
    session = Session.new(str(tmp_path))
    llm = MockLLM([
        _tool_response([
            {"name": "write_file", "args": {"path": "a.txt", "content": "first"}},
            {"name": "write_file", "args": {"path": "b.txt", "content": "second"}},
        ]),
        LLMResponse(content="done"),
    ])
    agent = AgentLoop(llm, session)
    agent.run("write")

    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "first"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "second"
