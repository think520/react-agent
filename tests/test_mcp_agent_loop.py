"""Tests for MCP prompt injection in core/agent_loop.py."""

import pytest

from core.agent_loop import MCP_PROMPT_MARKER, AgentLoop
from core.session import Session


class _FakeLLM:
    """Minimal stand-in for an LLM provider. Never actually called."""

    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        from providers.types import LLMResponse
        return LLMResponse(content="ok", tool_calls=[])


def _make_loop(skills_prompt=None, memory_prompt=None, mcp_prompt=None):
    session = Session.new("/tmp", max_messages=10)
    return AgentLoop(
        llm_provider=_FakeLLM(),
        session=session,
        skills_prompt=skills_prompt,
        memory_prompt=memory_prompt,
        mcp_prompt=mcp_prompt,
    )


def test_mcp_prompt_marker_exists():
    assert "bobodan:mcp-prompt" in MCP_PROMPT_MARKER


def test_no_mcp_prompt_when_none():
    loop = _make_loop()
    # run a no-op turn (LLM will return "ok" with no tool calls)
    list(loop.run_stream("hi"))
    # No system message should have the MCP marker
    sys_msgs = [m for m in loop.session.messages if m.get("role") == "system"]
    assert not any(MCP_PROMPT_MARKER in (m.get("content") or "") for m in sys_msgs)


def test_mcp_prompt_injected_on_first_turn():
    loop = _make_loop(mcp_prompt="## MCP Servers\n- `amap`: 12 tools")
    list(loop.run_stream("hi"))
    sys_msgs = [m for m in loop.session.messages if m.get("role") == "system"]
    assert any(MCP_PROMPT_MARKER in (m.get("content") or "") for m in sys_msgs)
    # The actual prompt text is present
    assert any("`amap`: 12 tools" in (m.get("content") or "") for m in sys_msgs)


def test_mcp_prompt_idempotent_across_turns():
    loop = _make_loop(mcp_prompt="## MCP Servers\n- `amap`")
    list(loop.run_stream("turn 1"))
    list(loop.run_stream("turn 2"))
    list(loop.run_stream("turn 3"))
    sys_msgs = [m for m in loop.session.messages if m.get("role") == "system"]
    mcp_injections = [m for m in sys_msgs if MCP_PROMPT_MARKER in (m.get("content") or "")]
    assert len(mcp_injections) == 1  # only injected once


def test_mcp_prompt_coexists_with_skills_and_memory():
    loop = _make_loop(
        skills_prompt="SKILLS_MARKER\n<skills>...</skills>",
        memory_prompt="MEMORY_MARKER\n<memory>...</memory>",
        mcp_prompt="## MCP Servers\n- `amap`",
    )
    list(loop.run_stream("hi"))
    sys_msgs = [m for m in loop.session.messages if m.get("role") == "system"]
    contents = "\n".join(m.get("content", "") for m in sys_msgs)
    assert "SKILLS_MARKER" in contents
    assert "MEMORY_MARKER" in contents
    assert MCP_PROMPT_MARKER in contents


def test_empty_mcp_prompt_not_injected():
    """If mcp_prompt is an empty string, don't add a system message."""
    loop = _make_loop(mcp_prompt="")
    list(loop.run_stream("hi"))
    sys_msgs = [m for m in loop.session.messages if m.get("role") == "system"]
    assert not any(MCP_PROMPT_MARKER in (m.get("content") or "") for m in sys_msgs)


def test_mcp_prompt_marker_does_not_show_in_prompt_body():
    """The marker is a hidden comment — should not be visible to the LLM
    as part of the meaningful content. We just check it's an HTML comment."""
    assert MCP_PROMPT_MARKER.startswith("<!--")
    assert MCP_PROMPT_MARKER.endswith("-->")
