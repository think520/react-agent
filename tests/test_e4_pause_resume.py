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
