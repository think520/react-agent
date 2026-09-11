"""E18 agent tools - the bank is readable and bookmarkable through execute_tool."""

from types import SimpleNamespace

from quiz.schema import Question, QuizAttempt
from quiz.store import QuizStore
from tools.base import execute_tool


def _seed(workspace: str):
    store = QuizStore(workspace)
    qid = store.add_question(Question(
        question="为什么 Dijkstra 不能处理负权边？",
        answer="负权会破坏贪心的前提",
        concepts=["图论"],
    ))
    session = store.create_session([qid])
    store.record_attempt(QuizAttempt(
        session_id=session.id,
        question_id=qid,
        user_answer="因为有环",
        is_correct=False,
        verdict="incorrect",
        feedback="负权会让已确定的路径变短。",
    ))
    return store, qid


def test_bank_tools_receive_the_session_workspace(tmp_path):
    workspace = str(tmp_path)
    store, qid = _seed(workspace)
    # execute_tool only injects parameters a tool declares, so the tools name
    # 'workspace' and never 'session'. Declaring the session object is what
    # silently pointed the first ask_user version at the project workspace (E4).
    session = SimpleNamespace(workspace_root=workspace, session_id="chat-1")

    overview = execute_tool("bank_overview", {}, session=session)
    assert overview.ok
    assert "1 道题" in overview.content
    assert overview.data["incorrect"] == 1

    listing = execute_tool("bank_list", {"state": "incorrect"}, session=session)
    assert listing.ok
    assert f"#{qid}" in listing.content
    assert "Dijkstra" in listing.content
    assert [item["id"] for item in listing.data["items"]] == [qid]


def test_bank_list_hides_the_answer_until_it_is_answered(tmp_path):
    workspace = str(tmp_path)
    store = QuizStore(workspace)
    qid = store.add_question(Question(
        question="BFS 的时间复杂度是多少？", answer="O(V+E)", concepts=["图论"],
    ))
    session = SimpleNamespace(workspace_root=workspace, session_id="chat-1")

    listing = execute_tool("bank_list", {}, session=session)
    assert listing.ok
    assert "O(V+E)" not in listing.content
    assert "answer" not in listing.data["items"][0]

    quiz_session = store.create_session([qid])
    store.record_attempt(QuizAttempt(
        session_id=quiz_session.id, question_id=qid, user_answer="O(E log V)",
        is_correct=False, verdict="incorrect",
    ))
    answered = execute_tool("bank_list", {}, session=session)
    assert "O(V+E)" in answered.content


def test_bank_bookmark_tool_marks_and_reports_missing(tmp_path):
    workspace = str(tmp_path)
    store, qid = _seed(workspace)
    session = SimpleNamespace(workspace_root=workspace, session_id="chat-1")

    marked = execute_tool(
        "bank_bookmark", {"question_id": qid, "bookmarked": True}, session=session
    )
    assert marked.ok
    assert marked.data == {"question_id": qid, "bookmarked": True}
    assert store.get_question(qid).bookmarked_at != ""

    removed = execute_tool(
        "bank_bookmark", {"question_id": qid, "bookmarked": False}, session=session
    )
    assert removed.data["bookmarked"] is False
    assert store.get_question(qid).bookmarked_at == ""

    missing = execute_tool("bank_bookmark", {"question_id": 9999}, session=session)
    assert not missing.ok


def test_bank_tools_are_registered_and_web_visible():
    from web.backend.routers.chat import _WEB_TOOL_NAMES
    from tools.base import TOOL_REGISTRY

    for name in ("bank_overview", "bank_list", "bank_bookmark"):
        assert name in TOOL_REGISTRY
        assert name in _WEB_TOOL_NAMES
    # The bank must never become the unbound chat-text practice path E13 closed.
    assert "quiz_start" not in _WEB_TOOL_NAMES
    assert "quiz_submit" not in _WEB_TOOL_NAMES
