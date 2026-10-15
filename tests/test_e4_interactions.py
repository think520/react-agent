"""E4 regression: the ask_user interaction lifecycle and its public projection."""

from __future__ import annotations

from service.interaction_service import (
    STATUS_ANSWERED,
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


def test_ask_user_lands_in_the_session_workspace(tmp_path):
    """Regression: register through the REAL execute_tool injection path.

    The first version declared ``session``, which execute_tool never passes to
    a tool. The record then landed in the project workspace (``.``) with an
    empty chat_session_id, so the answer endpoint -- which resolves the active
    library -- could not find it and answered 404.
    """
    from core.session import Session
    from tools.base import execute_tool

    session = Session.new(str(tmp_path))
    result = execute_tool(
        "ask_user",
        {"questions": [{"id": "q1", "prompt": "选一个", "options": ["甲", "乙"], "answer": "甲"}]},
        session,
    )

    assert result.ok is True
    artifact = result.artifacts[0]
    assert artifact["type"] == "ask_user"
    assert artifact["status"] == STATUS_AWAITING
    assert "answer" not in artifact["questions"][0]

    # The same workspace the answer endpoint resolves must hold the record.
    stored = InteractionService(session.workspace_root).get(artifact["artifact_id"])
    assert stored is not None
    assert stored["chat_session_id"] == session.session_id  # the injected id
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


def test_expiry_window_closes_orphan_rows_without_touching_open_ones(tmp_path):
    """The window is data hygiene: it never decides whether a card is answerable."""
    import sqlite3

    service = InteractionService(str(tmp_path))
    service.register("old", chat_session_id="c1", questions=[{"id": "q", "prompt": "?"}])
    service.register("new", chat_session_id="c1", questions=[{"id": "q", "prompt": "?"}])
    assert service.get("new")["expires_at"]  # every registration records the window

    conn = sqlite3.connect(service.db_path)
    conn.execute(
        "UPDATE interactions SET expires_at = '2000-01-01T00:00:00+00:00' WHERE interaction_id = 'old'"
    )
    conn.commit()
    conn.close()

    assert service.expire_stale("c1") == 1
    assert service.get("old")["closure"] == "expired"
    # The fresh one is untouched and still answerable.
    assert [row["interaction_id"] for row in service.list_open("c1")] == ["new"]


def test_lifecycle_really_passes_through_answered(tmp_path, monkeypatch):
    """W1 E4：路线里的四态（registered → awaiting_input → answered → graded）要真的能被观察到。

    旧实现把「已作答」和「已批改」压成一次更新（status=graded + closure=answered），
    于是 «answered» 这个状态**永远不会出现** —— 任何按路线实现的消费者、
    或"一次只推进一格"的投影都等不到它。
    """
    service = InteractionService(str(tmp_path))
    service.register("i1", chat_session_id="c1", questions=[{"id": "q1", "prompt": "?"}])
    assert service.get("i1")["status"] == STATUS_REGISTERED
    assert service.mark_awaiting("i1")["status"] == STATUS_AWAITING

    seen: list[str] = []
    original = service._update

    def spy(interaction_id, **fields):
        result = original(interaction_id, **fields)
        if "status" in fields:
            seen.append(service.get(interaction_id)["status"])
        return result

    monkeypatch.setattr(service, "_update", spy)
    record = service.answer("i1", [{"id": "q1", "answer": "甲"}])

    assert record["status"] == STATUS_GRADED
    assert seen == [STATUS_ANSWERED, STATUS_GRADED], seen
    # 中间态也要留下时间戳证据：answered_at 不晚于 graded_at。
    assert record["answered_at"] and record["graded_at"]
    assert record["answered_at"] <= record["graded_at"]


def test_multi_select_answers_are_graded_as_a_set(tmp_path):
    """W1 E4：multi_select 是路线里的承诺 —— 判分要按集合比，顺序不同不该判错。"""
    service = InteractionService(str(tmp_path))
    service.register("i1", chat_session_id="c1", questions=[{
        "id": "q1", "prompt": "选出两个正确的", "options": ["甲", "乙", "丙"],
        "answer": "甲, 丙", "multi_select": True,
    }])

    outcome = service.answer("i1", [{"id": "q1", "answer": "丙, 甲"}])["outcome"]

    assert outcome["graded"] is True, outcome
    assert outcome["correct"] == 1, outcome


def test_multi_select_partial_selection_is_not_correct(tmp_path):
    """只选对一半不是答对（多选不能因为"沾边"就给分）。"""
    service = InteractionService(str(tmp_path))
    service.register("i1", chat_session_id="c1", questions=[{
        "id": "q1", "prompt": "选出两个正确的", "options": ["甲", "乙", "丙"],
        "answer": "甲, 丙", "multi_select": True,
    }])

    outcome = service.answer("i1", [{"id": "q1", "answer": "甲"}])["outcome"]

    assert outcome["graded"] is True, outcome
    assert outcome["correct"] == 0, outcome


def test_multi_select_accepts_a_list_payload(tmp_path):
    """前端即使直接送数组（而不是逗号串）也要判对 —— 接口形状不该成为陷阱。"""
    service = InteractionService(str(tmp_path))
    service.register("i1", chat_session_id="c1", questions=[{
        "id": "q1", "prompt": "选出两个正确的", "options": ["甲", "乙", "丙"],
        "answer": ["甲", "丙"], "multi_select": True,
    }])

    outcome = service.answer("i1", [{"id": "q1", "answer": ["丙", "甲"]}])["outcome"]

    assert outcome["graded"] is True, outcome
    assert outcome["correct"] == 1, outcome
