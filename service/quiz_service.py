"""QuizService — business logic for question generation, quiz sessions, and review.

Used by both cli/repl.py and tools/quiz_tools.py.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from quiz.store import QuizStore
from quiz.generator import QuestionGenerator
from quiz.evaluator import QuizEvaluator
from quiz.schema import Question, QuizAttempt

logger = logging.getLogger(__name__)


def _ok(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, **kwargs}


def _err(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


def _get_llm_provider():
    from providers.factory import ProviderFactory
    return ProviderFactory.create_from_config()


_TYPE_LABELS = {
    "single_choice": "单选",
    "true_false": "判断",
    "short_answer": "简答",
}


class QuizService:
    """Stateless service: each method creates its own store/generator/evaluator."""

    def __init__(self, workspace: str = "."):
        self.workspace = workspace

    # --- Question generation ---

    def generate_questions(
        self,
        query: str,
        course: str | None = None,
        count: int = 5,
    ) -> dict[str, Any]:
        try:
            llm = _get_llm_provider()
        except Exception as e:
            return _err(f"LLM provider not available: {e}")

        store = QuizStore(self.workspace)
        generator = QuestionGenerator(self.workspace, llm)
        questions = generator.generate_from_query(query, course=course, count=count)

        if not questions:
            return _err(
                "未能生成题目。可能原因：\n"
                "1. 知识库中没有与该主题相关的资料（先用 /kb search 验证）\n"
                "2. 相关材料内容太少，不足以出题\n"
                "3. LLM 返回格式异常（已记录日志）\n"
                f"搜索主题: {query}"
            )

        saved_ids = []
        for q in questions:
            qid = store.add_question(q)
            q.id = qid
            saved_ids.append(qid)

        question_list = []
        for q in questions:
            question_list.append({
                "id": q.id,
                "type": q.type,
                "type_label": _TYPE_LABELS.get(q.type, q.type),
                "question": q.question,
                "options": q.options,
                "concepts": q.concepts,
                "difficulty": q.difficulty,
            })

        types = {}
        for q in questions:
            types[q.type] = types.get(q.type, 0) + 1

        return _ok(
            question_ids=saved_ids,
            count=len(saved_ids),
            types=types,
            questions=question_list,
        )

    # --- Quiz session ---

    def start_quiz(
        self,
        count: int = 5,
        course: str | None = None,
        question_type: str | None = None,
    ) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        questions = store.list_questions(course=course, qtype=question_type, limit=count)

        if len(questions) < count:
            try:
                llm = _get_llm_provider()
                generator = QuestionGenerator(self.workspace, llm)
                query = course or "课程重点知识"
                new_questions = generator.generate_from_query(
                    query, course=course, count=count - len(questions),
                )
                for q in new_questions:
                    qid = store.add_question(q)
                    q.id = qid
                questions.extend(new_questions)
            except Exception as e:
                logger.warning("Could not generate more questions: %s", e)

        if not questions:
            return _err("题库为空。请先使用 question_generate 生成题目，或确保知识库中有资料。")

        question_ids = [q.id for q in questions if q.id is not None]
        session = store.create_session(question_ids)

        question_list = []
        for q in questions:
            question_list.append({
                "id": q.id,
                "type": q.type,
                "type_label": _TYPE_LABELS.get(q.type, q.type),
                "question": q.question,
                "options": q.options,
                "difficulty": q.difficulty,
            })

        return _ok(
            session_id=session.id,
            question_ids=question_ids,
            questions=question_list,
        )

    # --- Submit answer ---

    def submit_answer(
        self,
        session_id: int,
        question_id: int,
        answer: str,
    ) -> dict[str, Any]:
        store = QuizStore(self.workspace)

        session = store.get_session(session_id)
        if not session:
            return _err(f"练习 session {session_id} 不存在。")

        question = store.get_question(question_id)
        if not question:
            return _err(f"题目 {question_id} 不存在。")

        if question_id not in session.question_ids:
            return _err(f"题目 {question_id} 不属于练习 session {session_id}。")

        try:
            llm = _get_llm_provider()
            evaluator = QuizEvaluator(llm)
        except Exception:
            evaluator = QuizEvaluator()

        is_correct, feedback = evaluator.evaluate(question, answer)

        attempt_record = QuizAttempt(
            session_id=session_id,
            question_id=question_id,
            user_answer=answer,
            is_correct=is_correct,
            feedback=feedback,
            answered_at=datetime.now(timezone.utc).isoformat(),
        )
        store.record_attempt(attempt_record)

        # Record learning effect
        try:
            from learning.quiz_integration import record_quiz_learning_effect
            record_quiz_learning_effect(
                workspace=self.workspace,
                question_concepts=question.concepts,
                is_correct=is_correct,
                feedback=feedback,
            )
        except Exception as e:
            logger.warning("Failed to record quiz learning effect: %s", e)

        # Check session completion
        session_completed = False
        try:
            from learning.quiz_integration import record_quiz_session_summary
            attempts = store.get_attempts_for_session(session_id)
            session_completed = record_quiz_session_summary(
                workspace=self.workspace,
                session_id=session_id,
                question_ids=session.question_ids,
                attempts=attempts,
            )
        except Exception as e:
            logger.warning("Failed to check session completion: %s", e)

        return _ok(
            is_correct=is_correct,
            feedback=feedback,
            correct_answer=question.answer,
            explanation=question.explanation,
            session_completed=session_completed,
        )

    # --- Review ---

    def get_wrong_answer_book(self, limit: int = 20) -> dict[str, Any]:
        from quiz.review import QuizReviewer
        store = QuizStore(self.workspace)
        reviewer = QuizReviewer(store)
        entries = reviewer.get_wrong_answer_book(limit=limit)
        return _ok(entries=entries)

    def get_weakness_analysis(self) -> dict[str, Any]:
        from quiz.review import QuizReviewer
        store = QuizStore(self.workspace)
        reviewer = QuizReviewer(store)
        analysis = reviewer.get_weakness_analysis()
        return _ok(analysis=analysis)

    # --- Stats ---

    def get_stats(self) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        counts = store.count_questions()
        if not counts:
            return _ok(total=0, counts={})
        return _ok(total=sum(counts.values()), counts=counts)
