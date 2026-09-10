"""E4 regression: ask_user pauses the turn and the answer resumes it in-protocol.

Covers the two halves the first E4 implementation was missing:
1. the pending tool_call is left unanswered on purpose (no tool result yet);
2. the resume fills that SAME tool_call with the answer, without appending a
   synthetic user message.
"""

from __future__ import annotations

from core.agent_loop import AgentLoop
from core.session import Session
from tests.llm_fake import ScriptedProvider

QUESTIONS = [{"id": "q1", "prompt": "你系统学算法主要为了什么？", "options": ["求职面试", "打牢基础"]}]


def _assistant_tool_call(session: Session) -> dict:
    for message in session.messages:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            return message["tool_calls"][0]
    raise AssertionError("no persisted assistant tool_call")


def _user_messages(session: Session) -> list[dict]:
    return [m for m in session.messages if m.get("role") == "user"]


def test_ask_user_pauses_the_turn_and_leaves_the_call_unanswered(tmp_path):
    provider = ScriptedProvider([{"tool": "ask_user", "args": {"questions": QUESTIONS}}])
    session = Session.new(str(tmp_path))
    agent = AgentLoop(provider, session)

    events = list(agent.run_stream("帮我安排学习路线"))

    done = [event for event in events if event["type"] == "assistant_done"][-1]
    assert done["termination_reason"] == "paused"
    assert done["pause"]["interaction_id"]

    # The tool_call is persisted, but deliberately has no tool result yet.
    assert _assistant_tool_call(session)["id"]
    assert [m for m in session.messages if m.get("role") == "tool"] == []
    # And no synthetic user message was invented.
    assert len(_user_messages(session)) == 1


def test_resume_fills_the_answer_as_the_tool_result(tmp_path):
    provider = ScriptedProvider([
        {"tool": "ask_user", "args": {"questions": QUESTIONS}},
        "好的，我按求职面试方向安排路线。",
    ])
    session = Session.new(str(tmp_path))
    agent = AgentLoop(provider, session)

    list(agent.run_stream("帮我安排学习路线"))
    tool_call_id = _assistant_tool_call(session)["id"]
    users_before = len(_user_messages(session))

    events = list(agent.run_stream(
        "",
        resume_tool_call_id=tool_call_id,
        resume_tool_content="[用户回答] 目标=求职面试",
    ))

    assert events[-1]["termination_reason"] == "final_answer"
    # The answer reached the model as a tool message on that same call id.
    sent = provider.last_messages() or []
    answers = [m for m in sent if m.get("role") == "tool" and m.get("tool_call_id") == tool_call_id]
    assert answers and "求职面试" in answers[0]["content"]
    # Resuming must not invent a user message.
    assert len(_user_messages(session)) == users_before


def test_resume_skips_prompt_and_memory_reinjection(tmp_path):
    provider = ScriptedProvider([
        {"tool": "ask_user", "args": {"questions": QUESTIONS}},
        "继续。",
    ])
    session = Session.new(str(tmp_path))
    agent = AgentLoop(provider, session, request_prompt="动态尾部")

    list(agent.run_stream("帮我安排学习路线"))
    tool_call_id = _assistant_tool_call(session)["id"]
    tails_before = sum(1 for m in session.messages if m.get("content") == "动态尾部")

    list(agent.run_stream("", resume_tool_call_id=tool_call_id, resume_tool_content="目标=求职面试"))

    tails_after = sum(1 for m in session.messages if m.get("content") == "动态尾部")
    assert tails_after <= tails_before


def test_new_message_fills_the_dangling_call_and_closes_the_question(tmp_path):
    """Action boundary (A): the session moving on closes the pending question."""
    from core.session import Session
    from service.interaction_service import InteractionService
    from tools.base import execute_tool
    from web.backend.routers.chat import _close_open_interactions

    session = Session.new(str(tmp_path))
    result = execute_tool("ask_user", {"questions": QUESTIONS}, session)
    interaction_id = result.artifacts[0]["artifact_id"]
    # The loop stamps the call id into the pause payload; the web layer stores it.
    InteractionService(str(tmp_path)).attach_tool_call(interaction_id, "call_001")

    assert _close_open_interactions(session, str(tmp_path)) == [interaction_id]

    # The dangling tool_call is filled in, so the next provider request is legal.
    tool_messages = [m for m in session.messages if m.get("role") == "tool"]
    assert tool_messages and tool_messages[0]["tool_call_id"] == "call_001"
    stored = InteractionService(str(tmp_path)).get(interaction_id)
    assert stored["closure"] == "skipped_by_next_message"


def test_resume_content_carries_answers_and_the_continue_directive():
    from web.backend.routers.chat import _resume_content

    text = _resume_content({
        "questions": [{"id": "q1", "prompt": "你系统学算法主要为了什么？"}],
        "answers": [{"id": "q1", "answer": "求职面试"}],
    })

    assert "求职面试" in text
    assert "你系统学算法主要为了什么？" in text
    # Without this directive models tend to reply with a bare acknowledgement.
    assert "Do not stop with an acknowledgement" in text

