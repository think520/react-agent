"""E15 regression: partial short answers are three-state end to end.

Covers the two inconsistencies found in the A0 reconciliation:
1. mastery mapping treated "partial" as a failure (is_correct=False -> needs_review);
2. the attempt did not persist the verdict, so the recap could not show it.
"""

from __future__ import annotations

from learning.progress import ProgressTracker
from learning.scheduler import ReviewScheduler
from learning.store import LearningStore


def test_partial_verdict_keeps_concept_in_learning(tmp_path):
    store = LearningStore(str(tmp_path))
    tracker = ProgressTracker(store, ReviewScheduler(store))

    results = tracker.update_from_quiz(["极限"], is_correct=False, verdict="partial")

    assert len(results) == 1
    assert results[0].status == "learning"
    assert results[0].interval_days == 1
    assert results[0].consecutive_correct == 0


def test_incorrect_verdict_still_resets_to_needs_review(tmp_path):
    store = LearningStore(str(tmp_path))
    tracker = ProgressTracker(store, ReviewScheduler(store))

    results = tracker.update_from_quiz(["极限"], is_correct=False, verdict="incorrect")

    assert results[0].status == "needs_review"


def test_partial_does_not_compound_into_mastery(tmp_path):
    store = LearningStore(str(tmp_path))
    tracker = ProgressTracker(store, ReviewScheduler(store))

    tracker.update_from_quiz(["极限"], is_correct=False, verdict="partial")
    again = tracker.update_from_quiz(["极限"], is_correct=False, verdict="partial")

    assert again[0].status == "learning"
    assert again[0].consecutive_correct == 0


def _attempt(store, question, session, *, verdict, is_correct, answer="答"):
    from quiz.schema import QuizAttempt

    return store.record_attempt(QuizAttempt(
        session_id=session.id, question_id=question.id,
        user_answer=answer, is_correct=is_correct, verdict=verdict, feedback="",
    ))


def _session_with_three_states(tmp_path):
    from quiz.schema import Question
    from quiz.store import QuizStore

    store = QuizStore(str(tmp_path))
    questions = [
        store.add_question(Question(question=f"第 {index} 题", answer="答案", concepts=[f"概念{index}"]))
        for index in range(1, 4)
    ]
    session = store.create_session(questions)
    right, partial, wrong = (
        store.get_question(questions[0]), store.get_question(questions[1]), store.get_question(questions[2]),
    )
    _attempt(store, right, session, verdict="correct", is_correct=True)
    _attempt(store, partial, session, verdict="partial", is_correct=False)
    _attempt(store, wrong, session, verdict="incorrect", is_correct=False)
    return store, session


def test_progress_counts_partial_separately_from_correct_and_wrong(tmp_path):
    """W1 E15：小结文案要与事实一致，前提是 progress 分得清三态。

    旧实现只有一个按 is_correct 算出来的 correct：partial 既不是"答对"、也不进错题本，
    而界面上只有"答对 X/Y"与"错题已加入复习队列"两句话 —— 两边对不上。
    """
    from service.quiz_service import QuizService

    _store, session = _session_with_three_states(tmp_path)

    progress = QuizService(str(tmp_path)).get_session_state(session.id)["progress"]

    assert progress["answered"] == 3, progress
    assert progress["correct"] == 1, progress
    assert progress["partial"] == 1, progress
    assert progress["wrong"] == 1, progress
    assert progress["total"] == 3, progress


def test_submit_answer_event_carries_the_verdict(tmp_path, monkeypatch):
    """W1 E15：学习轨迹（quiz_answered 事件）也要带上三态，不能只记 is_correct。"""
    from service.quiz_service import QuizService
    from service.memory_service import MemoryService

    from quiz.schema import Question
    from quiz.store import QuizStore

    captured: list = []
    monkeypatch.setattr(
        MemoryService, "record_event",
        lambda self, **kwargs: captured.append(kwargs),
    )
    store = QuizStore(str(tmp_path))
    question_id = store.add_question(Question(
        type="short_answer", question="光合作用是什么？", answer="光合作用", concepts=["光合作用"],
    ))
    session = store.create_session([question_id])

    result = QuizService(str(tmp_path)).submit_answer(session.id, question_id, "光合作用")

    assert result["ok"], result
    payload = captured[0]["payload"]
    # 事件里的 verdict 必须与落库的那次作答一致（不能只有 is_correct）。
    attempt = store.get_attempts_for_session(session.id)[0]
    assert payload["verdict"] == attempt.verdict == "correct", (payload, attempt.verdict)


def test_the_no_llm_fallback_still_says_partial(tmp_path):
    """W1 E15：没有模型时的兜底判分也要守三态约定（«partial ⇒ is_correct=False»）。

    旧代码把"基本正确"标成 «correct» + «is_correct=True»，与 LLM 路径的解析约定相反 ——
    于是同一句话在不同路径下被判成不同状态。
    """
    from quiz.evaluator import QuizEvaluator
    from quiz.schema import Question

    question = Question(question="光合作用是什么？", answer="光合作用", concepts=["光合作用"], type="short_answer")

    is_correct, feedback, verdict = QuizEvaluator().evaluate_with_verdict(question, "光合作用的过程")

    assert verdict == "partial", (is_correct, feedback, verdict)
    assert is_correct is False, (is_correct, feedback, verdict)
    assert "基本正确" in feedback
