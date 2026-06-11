"""Tests for learning.quiz_integration — quiz → memory + mastery bridge."""

import os
import glob

from learning.quiz_integration import record_quiz_learning_effect, record_quiz_session_summary
from learning.store import LearningStore
from learning.scheduler import ReviewScheduler
from learning.progress import ProgressTracker
from quiz.store import QuizStore
from quiz.schema import Question, QuizSession, QuizAttempt


def test_record_quiz_learning_effect_updates_mastery(tmp_path):
    """Mastery is updated for each concept after quiz submission."""
    ws = str(tmp_path)
    results = record_quiz_learning_effect(
        workspace=ws,
        question_concepts=["二叉树", "排序"],
        is_correct=True,
        feedback="回答正确",
    )

    assert len(results) == 2
    concepts = {m.concept for m in results}
    assert concepts == {"二叉树", "排序"}
    assert all(m.status == "learning" for m in results)
    assert all(m.score > 0 for m in results)
    assert all(m.review_count == 1 for m in results)


def test_record_quiz_learning_effect_wrong_answer(tmp_path):
    """Wrong answer sets status to needs_review."""
    ws = str(tmp_path)
    results = record_quiz_learning_effect(
        workspace=ws,
        question_concepts=["图算法"],
        is_correct=False,
        feedback="回答错误，正确答案是 B",
    )

    assert len(results) == 1
    assert results[0].status == "needs_review"
    assert results[0].consecutive_correct == 0


def test_record_quiz_learning_effect_two_correct_makes_mastered(tmp_path):
    """Two consecutive correct answers → mastered."""
    ws = str(tmp_path)
    record_quiz_learning_effect(ws, ["DP"], True, "正确")
    results = record_quiz_learning_effect(ws, ["DP"], True, "正确")

    assert len(results) == 1
    assert results[0].status == "mastered"
    assert results[0].consecutive_correct == 2


def test_record_quiz_learning_effect_writes_daily_memory(tmp_path):
    """Daily memory file is created with quiz entry."""
    ws = str(tmp_path)
    record_quiz_learning_effect(
        workspace=ws,
        question_concepts=["哈希表"],
        is_correct=True,
        feedback="很好",
    )

    daily_dir = os.path.join(ws, ".bobodan", "daily")
    assert os.path.isdir(daily_dir)
    files = glob.glob(os.path.join(daily_dir, "*.md"))
    assert len(files) == 1

    with open(files[0], encoding="utf-8") as f:
        content = f.read()
    assert "quiz" in content
    assert "哈希表" in content
    assert "做题" in content


def test_record_quiz_learning_effect_daily_memory_tags(tmp_path):
    """Daily memory frontmatter includes quiz and concept tags."""
    ws = str(tmp_path)
    record_quiz_learning_effect(ws, ["链表", "栈"], True, "正确")

    daily_dir = os.path.join(ws, ".bobodan", "daily")
    files = glob.glob(os.path.join(daily_dir, "*.md"))
    with open(files[0], encoding="utf-8") as f:
        content = f.read()

    assert "quiz" in content
    assert "链表" in content
    assert "栈" in content


def test_record_quiz_learning_effect_independent_of_agent(tmp_path):
    """Function is callable without any agent/tool context."""
    ws = str(tmp_path)

    # Call directly — no workspace session, no LLM, no tool registry needed
    results = record_quiz_learning_effect(ws, ["进程调度"], False, "错误")
    assert len(results) == 1

    # Verify mastery persisted in store
    store = LearningStore(ws)
    m = store.get_mastery("进程调度")
    assert m is not None
    assert m.status == "needs_review"


def test_record_quiz_learning_effect_empty_concepts(tmp_path):
    """Empty concepts list returns empty mastery list, still writes memory."""
    ws = str(tmp_path)
    results = record_quiz_learning_effect(ws, [], True, "正确")

    assert results == []

    # Memory still written
    daily_dir = os.path.join(ws, ".bobodan", "daily")
    files = glob.glob(os.path.join(daily_dir, "*.md"))
    assert len(files) == 1


def test_record_quiz_learning_effect_multiple_calls_accumulate(tmp_path):
    """Multiple quiz submissions accumulate mastery state."""
    ws = str(tmp_path)

    # First: correct on concept A
    record_quiz_learning_effect(ws, ["A"], True, "正确")
    # Second: wrong on concept A
    record_quiz_learning_effect(ws, ["A"], False, "错误")
    # Third: correct again on concept A
    results = record_quiz_learning_effect(ws, ["A"], True, "正确")

    m = results[0]
    assert m.review_count == 3
    assert m.consecutive_correct == 1  # reset after wrong, then 1 correct
    assert m.status == "learning"


# --- P0-2: Session summary tests ---

def _create_quiz_session(ws, concepts_list):
    """Helper: create a quiz session with questions. Returns (session, qstore, actual_question_ids)."""
    qstore = QuizStore(ws)
    qids = []
    for concepts in concepts_list:
        qid = qstore.add_question(Question(
            type="single_choice", question=f"Q{concepts}",
            answer="A", concepts=concepts if isinstance(concepts, list) else [concepts],
        ))
        qids.append(qid)
    session = qstore.create_session(qids)
    return session, qstore, qids


def test_session_summary_not_triggered_until_complete(tmp_path):
    """Summary is not written until all questions are answered."""
    ws = str(tmp_path)
    session, qstore, qids = _create_quiz_session(ws, ["概念A", "概念B", "概念C"])

    # Answer only 2 of 3
    attempts = [
        QuizAttempt(session_id=session.id, question_id=qids[0], is_correct=True),
        QuizAttempt(session_id=session.id, question_id=qids[1], is_correct=False),
    ]
    result = record_quiz_session_summary(ws, session.id, session.question_ids, attempts)
    assert result is False

    # No summary in daily memory
    daily_dir = os.path.join(ws, ".bobodan", "daily")
    if os.path.isdir(daily_dir):
        files = glob.glob(os.path.join(daily_dir, "*.md"))
        for f in files:
            with open(f, encoding="utf-8") as fh:
                assert "练习完成" not in fh.read()


def test_session_summary_triggered_on_completion(tmp_path):
    """Summary is written when all questions are answered."""
    ws = str(tmp_path)
    session, qstore, qids = _create_quiz_session(ws, ["概念A", "概念B", "概念C"])

    attempts = [
        QuizAttempt(session_id=session.id, question_id=qids[0], is_correct=True),
        QuizAttempt(session_id=session.id, question_id=qids[1], is_correct=True),
        QuizAttempt(session_id=session.id, question_id=qids[2], is_correct=False),
    ]
    result = record_quiz_session_summary(ws, session.id, session.question_ids, attempts)
    assert result is True

    # Summary in daily memory
    daily_dir = os.path.join(ws, ".bobodan", "daily")
    files = glob.glob(os.path.join(daily_dir, "*.md"))
    with open(files[0], encoding="utf-8") as f:
        content = f.read()
    assert "练习完成" in content
    assert "2" in content and "3" in content
    assert "67%" in content


def test_session_summary_marks_session_complete(tmp_path):
    """Session is marked as completed in the store."""
    ws = str(tmp_path)
    session, qstore, qids = _create_quiz_session(ws, ["X", "Y"])

    attempts = [
        QuizAttempt(session_id=session.id, question_id=qids[0], is_correct=True),
        QuizAttempt(session_id=session.id, question_id=qids[1], is_correct=True),
    ]
    record_quiz_session_summary(ws, session.id, session.question_ids, attempts)

    updated = qstore.get_session(session.id)
    assert updated.completed_at is not None


def test_session_summary_weak_concepts(tmp_path):
    """Summary includes weak concepts from wrong answers."""
    ws = str(tmp_path)
    session, qstore, qids = _create_quiz_session(ws, [["强概念"], ["弱概念"]])

    attempts = [
        QuizAttempt(session_id=session.id, question_id=qids[0], is_correct=True),
        QuizAttempt(session_id=session.id, question_id=qids[1], is_correct=False),
    ]
    record_quiz_session_summary(ws, session.id, session.question_ids, attempts)

    daily_dir = os.path.join(ws, ".bobodan", "daily")
    files = glob.glob(os.path.join(daily_dir, "*.md"))
    with open(files[0], encoding="utf-8") as f:
        content = f.read()
    assert "弱概念" in content


def test_session_summary_all_correct(tmp_path):
    """All correct session has no weak points."""
    ws = str(tmp_path)
    session, qstore, qids = _create_quiz_session(ws, ["A", "B"])

    attempts = [
        QuizAttempt(session_id=session.id, question_id=qids[0], is_correct=True),
        QuizAttempt(session_id=session.id, question_id=qids[1], is_correct=True),
    ]
    record_quiz_session_summary(ws, session.id, session.question_ids, attempts)

    daily_dir = os.path.join(ws, ".bobodan", "daily")
    files = glob.glob(os.path.join(daily_dir, "*.md"))
    with open(files[0], encoding="utf-8") as f:
        content = f.read()
    assert "100%" in content
    assert "无" in content
