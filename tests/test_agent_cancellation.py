"""A4 batch 3 (P0-1): pressing stop must actually stop the turn."""

from core.agent_loop import AgentLoop
from core.cancellation import CancelToken
from core.session import Session
from providers.types import LLMResponse, ToolCall


class _CountingLLM:
    name = "counting"
    model = "test"

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(content="done")


def _tool_call_response(name="probe_tool"):
    return LLMResponse(
        content="",
        tool_calls=[ToolCall(id="c1", name=name, arguments={})],
    )


def test_a_pre_cancelled_run_never_calls_the_provider(tmp_path):
    """The whole point: the money stops when the user stops."""
    token = CancelToken()
    token.cancel("client_disconnected")
    llm = _CountingLLM()
    agent = AgentLoop(llm, Session.new(str(tmp_path)), tools_schema=[], cancel_token=token)

    events = list(agent.run_stream("hi"))

    assert llm.calls == 0
    done = [event for event in events if event["type"] == "assistant_done"]
    assert done and done[-1]["termination_reason"] == "cancelled"


def test_cancelling_during_a_tool_call_ends_the_turn(tmp_path):
    """A cancelled turn stops at the next checkpoint instead of asking again."""
    token = CancelToken()
    llm = _CountingLLM([_tool_call_response()])

    def probe_tool(session=None, **kwargs):
        from tools.base import ToolResult

        token.cancel("client_disconnected")
        return ToolResult(ok=True, content="tool ran")

    from tools.base import TOOL_REGISTRY, register_tool

    register_tool("probe_tool", "probe", {"type": "object", "properties": {}}, probe_tool)
    try:
        agent = AgentLoop(llm, Session.new(str(tmp_path)), tools_schema=[], cancel_token=token)
        events = list(agent.run_stream("hi"))
    finally:
        TOOL_REGISTRY.pop("probe_tool", None)

    assert llm.calls == 1, "the tool ran once, then the loop stopped"
    done = [event for event in events if event["type"] == "assistant_done"]
    assert done and done[-1]["termination_reason"] == "cancelled"
