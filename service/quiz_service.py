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


def _get_llm_provider(config: dict | None = None):
    from service.runtime_service import RuntimeService
    if config is None:
        config = RuntimeService.load_default_config()
    return RuntimeService.create_provider(config)


_TYPE_LABELS = {
    "single_choice": "单选",
    "true_false": "判断",
    "short_answer": "简答",
}


class QuizService:
    """Stateless service: each method creates its own store/generator/evaluator."""

    def __init__(self, workspace: str = ".", config: dict | None = None):
        self.workspace = workspace
        self.config = config

    @staticmethod
    def _attribution(question: Question) -> dict[str, Any]:
        return {
            "kind": question.attribution_kind,
            "sources": question.sources,
        }

    def _question_for_practice(self, question: Question) -> dict[str, Any]:
        return {
            "id": question.id,
            "type": question.type,
            "type_label": _TYPE_LABELS.get(question.type, question.type),
            "question": question.question,
            "options": question.options,
            "concepts": question.concepts,
            "difficulty": question.difficulty,
            "attribution": self._attribution(question),
        }

    # --- Question generation ---

    def generate_questions(
        self,
        query: str,
        course: str | None = None,
        count: int = 5,
        document_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            llm = _get_llm_provider(self.config)
        except Exception as e:
            return _err(f"LLM provider not available: {e}")

        store = QuizStore(self.workspace)
        generator = QuestionGenerator(self.workspace, llm)
        questions = generator.generate_from_query(
            query,
            course=course,
            count=count,
            document_ids=document_ids,
        )

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
                "attribution": self._attribution(q),
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
        question_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        if question_ids:
            questions = [
                question for question_id in question_ids
                if (question := store.get_question(question_id)) is not None
            ][:count]
        else:
            questions = store.list_questions(course=course, qtype=question_type, limit=count)

        if not question_ids and len(questions) < count:
            try:
                llm = _get_llm_provider(self.config)
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

        question_list = [self._question_for_practice(q) for q in questions]

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
            llm = _get_llm_provider(self.config)
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
        mastery_changes = []
        try:
            from learning.quiz_integration import record_quiz_learning_effect
            updated = record_quiz_learning_effect(
                workspace=self.workspace,
                question_concepts=question.concepts,
                is_correct=is_correct,
                feedback=feedback,
            )
            mastery_changes = [
                {
                    "concept": item.concept,
                    "status": item.status,
                    "score": item.score,
                    "next_review": item.next_review,
                }
                for item in updated
            ]
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

        session_state = self.get_session_state(session_id)
        progress = session_state.get("progress", {}) if session_state.get("ok") else {}

        return _ok(
            is_correct=is_correct,
            feedback=feedback,
            correct_answer=question.answer,
            explanation=question.explanation,
            concepts=question.concepts,
            attribution=self._attribution(question),
            mastery_changes=mastery_changes,
            progress=progress,
            session_completed=session_completed,
        )

    def get_session_state(self, session_id: int) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        session = store.get_session(session_id)
        if not session:
            return _err(f"练习 session {session_id} 不存在。")

        questions = store.get_questions_by_ids(session.question_ids)
        attempts = store.get_attempts_for_session(session_id)
        latest_attempts = {}
        for attempt in attempts:
            latest_attempts[attempt.question_id] = attempt

        answered_count = len(latest_attempts)
        correct_count = sum(1 for attempt in latest_attempts.values() if attempt.is_correct)
        total = len(session.question_ids)
        current_index = total
        for index, question_id in enumerate(session.question_ids):
            if question_id not in latest_attempts:
                current_index = index
                break

        attempt_items = [
            {
                "question_id": attempt.question_id,
                "user_answer": attempt.user_answer,
                "is_correct": attempt.is_correct,
                "feedback": attempt.feedback,
                "answered_at": attempt.answered_at,
            }
            for attempt in latest_attempts.values()
        ]

        return _ok(
            practice_session_id=session.id,
            status=session.status,
            started_at=session.started_at,
            updated_at=session.updated_at,
            completed_at=session.completed_at,
            questions=[self._question_for_practice(question) for question in questions],
            attempts=attempt_items,
            progress={
                "answered": answered_count,
                "total": total,
                "correct": correct_count,
                "current_index": current_index,
                "completed": session.status == "completed",
            },
        )

    def list_active_sessions(self, limit: int = 10) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        sessions = store.list_active_sessions(limit=limit)
        return _ok(sessions=[
            {
                "practice_session_id": session.id,
                "started_at": session.started_at,
                "updated_at": session.updated_at,
                "question_count": len(session.question_ids),
            }
            for session in sessions
        ])

    def abandon_session(self, session_id: int) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        if not store.get_session(session_id):
            return _err(f"练习 session {session_id} 不存在。")
        store.abandon_session(session_id)
        return _ok(practice_session_id=session_id, status="abandoned")

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
