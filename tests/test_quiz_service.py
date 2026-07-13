"""Tests for QuizService — service layer for question generation, quiz sessions, and review."""

import pytest

from quiz.store import QuizStore
from quiz.schema import Question, QuizSession, QuizAttempt
from service.quiz_service import QuizService


@pytest.fixture
def workspace(tmp_path):
    return str(tmp_path)


@pytest.fixture
def svc(workspace):
    return QuizService(workspace)


@pytest.fixture
def store(workspace):
    return QuizStore(workspace)


def _make_question(store, qid=None, qtype="single_choice", concepts=None):
    q = Question(
        type=qtype,
        question="What is 1+1?",
        options=["A. 1", "B. 2", "C. 3"] if qtype == "single_choice" else [],
        answer="B" if qtype == "single_choice" else "true",
        explanation="Basic math",
        concepts=concepts or ["math"],
        difficulty="easy",
    )
    if qid:
        q.id = qid
    else:
        q.id = store.add_question(q)
    return q


# --- generate_questions ---

def test_generate_questions_no_llm(svc):
    """Without LLM, should return error."""
    result = svc.generate_questions("test topic")
    assert not result["ok"]
    assert "LLM" in result["error"]


# --- start_quiz ---

def test_start_quiz_empty(store, svc):
    """No questions in store and no LLM → error."""
    result = svc.start_quiz(count=3)
    assert not result["ok"]
    assert "题库为空" in result["error"]


def test_start_quiz_with_existing_questions(store, svc):
    _make_question(store, qtype="single_choice")
    _make_question(store, qtype="true_false")

    result = svc.start_quiz(count=2)
    assert result["ok"]
    assert result["session_id"] is not None
    assert len(result["question_ids"]) == 2
    assert len(result["questions"]) == 2
    # Questions should not contain answers
    for q in result["questions"]:
        assert "id" in q
        assert "type" in q
        assert "question" in q
        assert "attribution" in q


def test_start_quiz_uses_only_requested_question_ids(store, svc):
    first = _make_question(store, qtype="single_choice")
    second = _make_question(store, qtype="true_false")
    _make_question(store, qtype="short_answer")

    result = svc.start_quiz(count=5, question_ids=[second.id, first.id])

    assert result["ok"]
    assert result["question_ids"] == [second.id, first.id]
    assert [item["id"] for item in result["questions"]] == [second.id, first.id]


def test_start_quiz_with_type_filter(store, svc):
    _make_question(store, qtype="single_choice")
    _make_question(store, qtype="true_false")

    result = svc.start_quiz(count=2, question_type="single_choice")
    assert result["ok"]
    assert len(result["questions"]) == 1
    assert result["questions"][0]["type"] == "single_choice"


# --- submit_answer ---

def test_submit_answer_correct(store, svc):
    q = _make_question(store, qtype="single_choice")
    session = store.create_session([q.id])

    result = svc.submit_answer(session.id, q.id, "B")
    assert result["ok"]
    assert result["is_correct"] is True
    assert "feedback" in result
    assert result["correct_answer"] == "B"
    assert result["progress"]["completed"] is True
    assert result["session_completed"] is True
    assert result["concepts"] == ["math"]
    assert result["mastery_changes"]


def test_submit_answer_wrong(store, svc):
    q = _make_question(store, qtype="single_choice")
    session = store.create_session([q.id])

    result = svc.submit_answer(session.id, q.id, "A")
    assert result["ok"]
    assert result["is_correct"] is False


def test_submit_answer_invalid_session(svc):
    result = svc.submit_answer(999, 1, "A")
    assert not result["ok"]
    assert "不存在" in result["error"]


def test_submit_answer_invalid_question(store, svc):
    session = store.create_session([1])
    result = svc.submit_answer(session.id, 999, "A")
    assert not result["ok"]
    assert "不存在" in result["error"]


def test_submit_answer_question_not_in_session(store, svc):
    q1 = _make_question(store, qtype="single_choice")
    q2 = _make_question(store, qtype="single_choice")
    session = store.create_session([q1.id])

    result = svc.submit_answer(session.id, q2.id, "B")
    assert not result["ok"]
    assert "不属于" in result["error"]


def test_session_state_and_abandon(store, svc):
    q1 = _make_question(store)
    q2 = _make_question(store)
    session = store.create_session([q1.id, q2.id])
    store.record_attempt(QuizAttempt(
        session_id=session.id,
        question_id=q1.id,
        user_answer="B",
        is_correct=True,
    ))

    state = svc.get_session_state(session.id)
    assert state["ok"]
    assert state["progress"] == {
        "answered": 1,
        "total": 2,
        "correct": 1,
        "current_index": 1,
        "completed": False,
    }
    assert state["attempts"][0]["question_id"] == q1.id

    abandoned = svc.abandon_session(session.id)
    assert abandoned["status"] == "abandoned"
    assert svc.list_active_sessions()["sessions"] == []


# --- get_wrong_answer_book ---

def test_get_wrong_answer_book_empty(svc):
    result = svc.get_wrong_answer_book()
    assert result["ok"]
    assert result["entries"] == []


def test_get_wrong_answer_book_with_data(store, svc):
    q = _make_question(store, qtype="single_choice")
    session = store.create_session([q.id])
    attempt = QuizAttempt(
        session_id=session.id, question_id=q.id,
        user_answer="A", is_correct=False, feedback="wrong",
    )
    store.record_attempt(attempt)

    result = svc.get_wrong_answer_book()
    assert result["ok"]
    assert len(result["entries"]) == 1


# --- get_weakness_analysis ---

def test_get_weakness_analysis_empty(svc):
    result = svc.get_weakness_analysis()
    assert result["ok"]
    assert result["analysis"] == []


def test_get_weakness_analysis_with_data(store, svc):
    q = _make_question(store, qtype="single_choice", concepts=["OS"])
    session = store.create_session([q.id])
    attempt = QuizAttempt(
        session_id=session.id, question_id=q.id,
        user_answer="A", is_correct=False, feedback="wrong",
    )
    store.record_attempt(attempt)

    result = svc.get_weakness_analysis()
    assert result["ok"]
    assert len(result["analysis"]) >= 1


# --- get_stats ---

def test_get_stats_empty(svc):
    result = svc.get_stats()
    assert result["ok"]
    assert result["total"] == 0


def test_get_stats_with_data(store, svc):
    _make_question(store, qtype="single_choice")
    _make_question(store, qtype="true_false")

    result = svc.get_stats()
    assert result["ok"]
    assert result["total"] == 2
    assert result["counts"]["single_choice"] == 1
    assert result["counts"]["true_false"] == 1


# --- Data contract ---

def test_all_results_have_ok_field(svc, store):
    q = _make_question(store, qtype="single_choice")
    session = store.create_session([q.id])

    methods = [
        svc.get_stats(),
        svc.get_wrong_answer_book(),
        svc.get_weakness_analysis(),
        svc.start_quiz(count=1),
        svc.submit_answer(session.id, q.id, "B"),
    ]
    for r in methods:
        assert "ok" in r, f"Missing 'ok' in {r}"
