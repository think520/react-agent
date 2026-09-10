"""E4 regression: the ask_user interaction lifecycle and its public projection."""

from __future__ import annotations

from service.interaction_service import (
    STATUS_AWAITING,
    STATUS_GRADED,
    STATUS_REGISTERED,
    InteractionService,
)
from tools.ask_user import ask_user


def test_lifecycle_transitions(tmp_path):
    service = InteractionService(str(tmp_path))
    record = service.register(
        "i1",
        chat_session_id="c1",
        questions=[{"id": "q1", "prompt": "选一个", "options": ["甲", "乙"]}],
    )
    assert record["status"] == STATUS_REGISTERED

    assert service.mark_awaiting("i1")["status"] == STATUS_AWAITING
    assert [item["interaction_id"] for item in service.list_open("c1")] == ["i1"]

    answered = service.answer("i1", [{"id": "q1", "answer": "甲"}])
    assert answered["status"] == STATUS_GRADED
    # No correct option was supplied, so nothing is graded but the lifecycle ends.
    assert answered["outcome"]["graded"] is False
    assert service.list_open("c1") == []


def test_answer_is_idempotent(tmp_path):
    service = InteractionService(str(tmp_path))
    service.register("i1", chat_session_id="c1", questions=[{"id": "q1", "prompt": "?"}])

    first = service.answer("i1", [{"id": "q1", "answer": "第一次"}])
    second = service.answer("i1", [{"id": "q1", "answer": "第二次"}])

    assert second["answers"][0]["answer"] == "第一次"
    assert first["graded_at"] == second["graded_at"]


def test_grading_is_deterministic(tmp_path):
    service = InteractionService(str(tmp_path))
    service.register(
        "i1",
        chat_session_id="c1",
        questions=[
            {"id": "q1", "prompt": "甲还是乙", "options": ["甲", "乙"], "answer": "甲"},
            {"id": "q2", "prompt": "开放题"},
        ],
    )

    graded = service.answer("i1", [{"id": "q1", "answer": "乙"}])

    assert graded["outcome"]["graded"] is True
    assert graded["outcome"]["correct"] == 0
    assert graded["outcome"]["total"] == 2


def test_unknown_interaction_returns_none(tmp_path):
    service = InteractionService(str(tmp_path))
    assert service.get("missing") is None
    assert service.answer("missing", []) is None


def test_open_list_is_scoped_to_the_session(tmp_path):
    service = InteractionService(str(tmp_path))
    service.register("i1", chat_session_id="c1", questions=[{"id": "q", "prompt": "?"}])
    service.register("i2", chat_session_id="c2", questions=[{"id": "q", "prompt": "?"}])

    assert [item["interaction_id"] for item in service.list_open("c1")] == ["i1"]


def test_ask_user_registers_and_never_leaks_the_answer(tmp_path):
    class FakeSession:
        workspace_root = str(tmp_path)
        session_id = "chat-1"

    result = ask_user(
        [{"id": "q1", "prompt": "选一个", "options": ["甲", "乙"], "answer": "甲"}],
        session=FakeSession(),
    )

    assert result.ok is True
    artifact = result.artifacts[0]
    assert artifact["type"] == "ask_user"
    assert artifact["status"] == STATUS_AWAITING
    assert "answer" not in artifact["questions"][0]

    stored = InteractionService(str(tmp_path)).get(artifact["artifact_id"])
    assert stored is not None
    assert stored["chat_session_id"] == "chat-1"
    # The correct option lives only in the server-side record, for grading.
    assert stored["questions"][0]["answer"] == "甲"


def test_ask_user_rejects_empty_questions():
    result = ask_user([])
    assert result.ok is False


def test_public_projection_strips_answers():
    from web.backend.routers.chat import _public_interaction

    payload = _public_interaction({
        "interaction_id": "i1",
        "status": STATUS_GRADED,
        "questions": [{"id": "q1", "prompt": "?", "answer": "甲"}],
        "answers": [{"id": "q1", "answer": "乙"}],
        "outcome": {"graded": True},
    })

    assert payload["artifact_id"] == "i1"
    assert "answer" not in payload["questions"][0]
    assert payload["outcome"]["graded"] is True


def test_web_agent_can_ask_the_user():
    from web.backend.routers.chat import _WEB_TOOL_NAMES

    assert "ask_user" in _WEB_TOOL_NAMES
