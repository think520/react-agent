"""P0-2/P0-3: a hanging tool must degrade, not hang the turn."""

from tools.base import ToolResult
from tools.timeouts import TOOL_TIMEOUTS, run_with_timeout, tool_timeout


def test_tools_without_a_configured_timeout_run_inline():
    assert tool_timeout("read_file") is None
    assert tool_timeout("delegate_doc_reader") == 60.0
    assert tool_timeout("nonexistent_tool") is None
    assert "read_file" not in TOOL_TIMEOUTS


def test_a_fast_tool_returns_its_result():
    result = run_with_timeout(lambda: ToolResult(ok=True, content="ok"), 5.0, "probe")

    assert result.ok is True
    assert result.content == "ok"


def test_a_hanging_tool_becomes_a_structured_timeout():
    """The audit point: the turn must not be held hostage by one tool."""
    import time

    def hangs() -> ToolResult:
        time.sleep(5)
        return ToolResult(ok=True, content="too late")

    started = time.monotonic()
    result = run_with_timeout(hangs, 0.2, "probe_slow")
    elapsed = time.monotonic() - started

    assert result.ok is False
    assert result.data["code"] == "tool_timeout"
    assert "probe_slow" in result.content
    assert elapsed < 3, "the caller must not wait for the abandoned worker"


def test_a_loop_turns_a_hanging_tool_into_a_result(tmp_path, monkeypatch):
    """End to end: the session survives and the model is told, instead of the
    turn hanging until the user gives up."""
    import time

    from core.agent_loop import AgentLoop
    from core.session import Session
    from providers.types import LLMResponse, ToolCall
    from tools.base import TOOL_REGISTRY, ToolResult, register_tool
    from tools import timeouts as timeout_module

    class _LLM:
        name = "scripted"
        model = "test"

        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(content="", tool_calls=[ToolCall(id="c1", name="probe_slow", arguments={})])
            return LLMResponse(content="done")

    def probe_slow(session=None, **kwargs):
        time.sleep(5)
        return ToolResult(ok=True, content="too late")

    register_tool("probe_slow", "slow probe", {"type": "object", "properties": {}}, probe_slow)
    monkeypatch.setitem(timeout_module.TOOL_TIMEOUTS, "probe_slow", 0.2)
    try:
        agent = AgentLoop(_LLM(), Session.new(str(tmp_path)), tools_schema=[])
        events = list(agent.run_stream("hi"))
    finally:
        TOOL_REGISTRY.pop("probe_slow", None)

    tool_end = [event for event in events if event["type"] == "tool_end"]
    assert tool_end and tool_end[-1]["ok"] is False
    assert "超过" in tool_end[-1]["content"]
    done = [event for event in events if event["type"] == "assistant_done"]
    assert done and done[-1]["termination_reason"] == "final_answer"

def test_a_raising_tool_becomes_a_result_not_an_exception():
    def boom() -> ToolResult:
        raise RuntimeError("kaboom")

    result = run_with_timeout(boom, 5.0, "probe_boom")

    assert result.ok is False
    assert "kaboom" in result.content
