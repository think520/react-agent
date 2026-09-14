"""P0-8 / P1-11: context projection must stay legal for a strict provider."""

from core.session_compactor import (
    INTERRUPTED_TOOL_RESULT,
    project_context,
    repair_tool_pairing,
    structural_checkpoint,
)


def _assistant_call(call_id, name="rag_search"):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}],
    }


def test_resolve_context_window_falls_back_conservatively():
    """P0-8: nothing configured a window, so compaction was dead code."""
    from core.session_compactor import DEFAULT_CONTEXT_WINDOW, resolve_context_window

    assert resolve_context_window(None) == DEFAULT_CONTEXT_WINDOW
    assert resolve_context_window({}) == DEFAULT_CONTEXT_WINDOW
    assert resolve_context_window({"agent": {"context_window": 0}}) == DEFAULT_CONTEXT_WINDOW
    assert resolve_context_window({"agent": {"context_window": "abc"}}) == DEFAULT_CONTEXT_WINDOW
    assert resolve_context_window({"agent": {"context_window": 8000}}) == 8000


def test_agent_service_forwards_the_context_window(tmp_path, monkeypatch):
    """The wiring, not just the resolver: the loop must receive a window."""
    captured: dict = {}

    class FakeLoop:
        def __init__(self, *_args, **kwargs):
            captured.update(kwargs)

        def run_stream(self, *_args, **_kwargs):
            return iter(())

    monkeypatch.setattr("core.agent_loop.AgentLoop", FakeLoop)
    monkeypatch.setattr("core.runtime.guard_provider", lambda provider: provider)

    from core.session import Session
    from service.agent_service import AgentService

    list(AgentService.run_stream(
        session=Session.new(str(tmp_path)),
        user_input="hi",
        provider=object(),
        tools_schema=[],
        context_window=4096,
    ))

    assert captured["context_window"] == 4096

def test_tail_cut_never_starts_inside_a_tool_block():
    """The old cut was `rest[-tail:]`, which could start on a tool response and
    orphan its assistant(tool_calls) - a strict provider answers 400."""
    messages = [
        {"role": "user", "content": "第一个问题"},
        _assistant_call("c1"),
        {"role": "tool", "tool_call_id": "c1", "content": "结果一"},
        {"role": "user", "content": "第二个问题"},
        _assistant_call("c2"),
        {"role": "tool", "tool_call_id": "c2", "content": "结果二"},
    ]

    projected = project_context(messages, tail=2)

    roles = [message["role"] for message in projected]
    assert roles.count("tool") == 1
    tool_index = roles.index("tool")
    assert roles[tool_index - 1] == "assistant"
    assert projected[tool_index - 1].get("tool_calls")


def test_projection_carries_a_deterministic_checkpoint():
    """Summarizing an over-window context with the model needs the budget we
    just ran out of, so the checkpoint is extracted by rule."""
    dropped = [
        {"role": "user", "content": "帮我把 Dijkstra 的证明整理出来"},
        _assistant_call("c1", "rag_search"),
        {"role": "tool", "tool_call_id": "c1", "content": "资料片段"},
    ]
    checkpoint = structural_checkpoint(dropped)
    rendered = checkpoint.to_message()["content"]
    assert "Dijkstra" in rendered
    assert "rag_search" in rendered
    assert not checkpoint.is_empty()


class _CapturingLLM:
    name = "capture"
    model = "test"

    def __init__(self):
        self.seen: list[list[dict]] = []

    def complete(self, messages, tools=None):
        from providers.base import LLMResponse

        self.seen.append([dict(message) for message in messages])
        return LLMResponse(content="done")


def test_the_loop_repairs_a_dangling_tool_call_before_sending(tmp_path):
    """P1-11: pausing on ask_user and never resuming left an assistant
    tool_call with no response; the next user message made it illegal."""
    from core.agent_loop import AgentLoop
    from core.session import Session

    session = Session.new(str(tmp_path))
    session.add_message_with_tool_calls("assistant", "", [
        {"id": "c1", "type": "function", "function": {"name": "ask_user", "arguments": "{}"}},
    ])

    llm = _CapturingLLM()
    agent = AgentLoop(llm, session, tools_schema=[])
    list(agent.run_stream("换个话题"))

    sent = llm.seen[0]
    roles = [message["role"] for message in sent]
    # the synthetic response lands directly after the call it answers
    assert roles[:2] == ["assistant", "tool"], roles
    assert "user" in roles
    assert sent[1]["tool_call_id"] == "c1"
    assert sent[1]["content"] == INTERRUPTED_TOOL_RESULT

def test_repair_drops_orphan_tool_responses():
    messages = [
        {"role": "user", "content": "问题"},
        {"role": "tool", "tool_call_id": "ghost", "content": "孤儿结果"},
        {"role": "assistant", "content": "回答"},
    ]
    repaired = repair_tool_pairing(messages)
    assert [message["role"] for message in repaired] == ["user", "assistant"]


def test_repair_backfills_a_missing_tool_response():
    """P1-11: pausing on ask_user and never resuming left an assistant
    tool_call with no response, and the next user message made it illegal."""
    messages = [
        _assistant_call("c1", "ask_user"),
        {"role": "user", "content": "算了，换个话题"},
    ]
    repaired = repair_tool_pairing(messages)
    roles = [message["role"] for message in repaired]
    assert roles == ["assistant", "tool", "user"]
    assert repaired[1]["tool_call_id"] == "c1"
    assert repaired[1]["content"] == INTERRUPTED_TOOL_RESULT


def test_repair_is_a_no_op_for_a_healthy_transcript():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "问题"},
        _assistant_call("c1"),
        {"role": "tool", "tool_call_id": "c1", "content": "结果"},
        {"role": "assistant", "content": "回答"},
    ]
    assert repair_tool_pairing(messages) == messages
