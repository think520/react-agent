"""QuizService — business logic for question generation, quiz sessions, and review.

Used by both cli/repl.py and tools/quiz_tools.py.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from quiz.store import QuizStore
from quiz.generator import QuestionGenerator
from quiz.evaluator import GradingError, QuizEvaluator
from quiz.schema import Question, QuizAttempt
from service._result import err as _err, ok as _ok

logger = logging.getLogger(__name__)


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
        web_research_id: str | None = None,
        web_confirmed: bool = False,
        search_permission: str = "ask",
        search_provider: str = "auto",
        jina_fallback: bool = True,
        memory_enabled: bool = True,
    ) -> dict[str, Any]:
        try:
            llm = _get_llm_provider(self.config)
        except Exception as e:
            return _err(f"LLM provider not available: {e}")

        store = QuizStore(self.workspace)
        generator = QuestionGenerator(self.workspace, llm)
        personalization: list[dict[str, Any]] = []
        if memory_enabled:
            try:
                from service.memory_service import MemoryService
                context = MemoryService(self.workspace).personalization_context(query)
                generator.personalization_context = context.get("content", "")
                personalization = context.get("references", [])
            except Exception as exc:
                logger.warning("Could not load question personalization: %s", exc)
        web_attempted = False
        active_web_research_id = web_research_id
        if active_web_research_id:
            from service.research_service import ResearchService
            try:
                evidence = ResearchService(self.workspace).evidence(active_web_research_id)
            except FileNotFoundError:
                return _err("选中的网页证据不存在或已失效。")
            questions = generator.generate_from_web_evidence(evidence["content"], evidence["sources"], count=count)
        else:
            questions = generator.generate_from_query(
                query,
                course=course,
                count=count,
                document_ids=document_ids,
            )

        if not questions and not active_web_research_id and generator.failure_kind == "no_evidence":
            if search_permission == "auto" or web_confirmed:
                web_attempted = True
                from service.research_service import ResearchService
                try:
                    research = ResearchService(self.workspace).auto_research(
                        f"practice-{uuid.uuid4().hex}",
                        generator.resolved_query or query,
                        provider_name=search_provider,
                        jina_fallback=jina_fallback,
                    )
                except Exception as exc:
                    logger.warning("Practice web research failed: %s", exc)
                    research = None
                if research and research.get("sources"):
                    active_web_research_id = research["research_id"]
                    questions = generator.generate_from_web_evidence(
                        research["content"],
                        research["sources"],
                        count=count,
                    )
            else:
                return _ok(
                    status="web_consent_required",
                    query=generator.resolved_query or query,
                    reason="当前资料库中没有找到足够的相关内容。确认后可以联网读取公开资料并据此出题。",
                    suggested_query=(generator.resolved_query if generator.resolved_query != query else None),
                )

        if not questions:
            if generator.failure_kind == "invalid_model_output":
                return _err("模型没有返回可用的题目格式。已自动重试一次，请稍后再试。")
            if web_attempted:
                return _err("本地资料不足，联网来源也暂时没有返回可用于出题的正文。请调整主题或稍后重试。")
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
            status="ready",
            question_ids=saved_ids,
            count=len(saved_ids),
            types=types,
            questions=question_list,
            resolved_query=generator.resolved_query or query,
            web_research_id=active_web_research_id,
            personalization=personalization,
        )

    # --- Quiz session ---

    def start_quiz(
        self,
        count: int = 5,
        course: str | None = None,
        question_type: str | None = None,
        question_ids: list[int] | None = None,
        origin: str = "practice",
        personalization: list[dict] | None = None,
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
        session = store.create_session(
            question_ids,
            origin=origin,
            personalization=personalization,
        )

        if session.origin == "review":
            try:
                from service.memory_service import MemoryService
                MemoryService(self.workspace).record_event(
                    event_type="review_started",
                    source_type="review",
                    source_id=str(session.id),
                    payload={"question_ids": question_ids},
                    dedupe_key=f"review_started:{session.id}",
                )
            except Exception as exc:
                logger.warning("Could not record review start: %s", exc)

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

        try:
            is_correct, feedback, verdict = evaluator.evaluate_with_verdict(question, answer)
        except GradingError as exc:
            logger.warning("Grading unavailable for question %s: %s", question_id, exc)
            return _err(
                "批改服务暂时不可用，本次作答未记录，请稍后重试。",
                code="grading_unavailable",
            )

        attempt_record = QuizAttempt(
            session_id=session_id,
            question_id=question_id,
            user_answer=answer,
            is_correct=is_correct,
            verdict=verdict,
            feedback=feedback,
            answered_at=datetime.now(timezone.utc).isoformat(),
        )
        attempt_id = store.record_attempt(attempt_record)

        try:
            from service.memory_service import MemoryService
            MemoryService(self.workspace).record_event(
                event_type="quiz_answered",
                source_type="quiz",
                source_id=str(attempt_id),
                concept=question.concepts[0] if question.concepts else None,
                payload={
                    "session_id": session_id,
                    "question_id": question_id,
                    "origin": session.origin,
                    "is_correct": is_correct,
                    "concepts": question.concepts,
                },
                dedupe_key=f"quiz_answered:{attempt_id}",
            )
        except Exception as exc:
            logger.warning("Could not record quiz event: %s", exc)

        # Record learning effect
        mastery_changes = []
        try:
            from learning.quiz_integration import record_quiz_learning_effect
            updated = record_quiz_learning_effect(
                workspace=self.workspace,
                question_concepts=question.concepts,
                is_correct=is_correct,
                feedback=feedback,
                verdict=verdict,
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

        if session_completed:
            try:
                from service.memory_service import MemoryService
                attempts = store.get_attempts_for_session(session_id)
                correct = sum(1 for item in attempts if item.is_correct)
                event_type = "review_completed" if session.origin == "review" else "practice_completed"
                source_type = "review" if session.origin == "review" else "quiz"
                MemoryService(self.workspace).record_event(
                    event_type=event_type,
                    source_type=source_type,
                    source_id=str(session_id),
                    payload={
                        "origin": session.origin,
                        "question_count": len(session.question_ids),
                        "correct": correct,
                    },
                    dedupe_key=f"{event_type}:{session_id}",
                )
            except Exception as exc:
                logger.warning("Could not record session completion: %s", exc)

        session_state = self.get_session_state(session_id)
        progress = session_state.get("progress", {}) if session_state.get("ok") else {}

        return _ok(
            is_correct=is_correct,
            verdict=verdict,
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
                "verdict": attempt.verdict,
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
            origin=session.origin,
            personalization=session.personalization,
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
                "origin": session.origin,
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

    def generate_wrong_answer_variant(self, attempt_id: int) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        entry = store.get_wrong_answer(attempt_id)
        if not entry:
            return _err("错题记录不存在。", code="wrong_answer_not_found")
        original = store.get_question(entry["question_id"])
        if not original:
            return _err("原题不存在，无法生成变式题。", code="question_not_found")

        chunk_ids = [
            str(source.get("chunk_id"))
            for source in original.sources
            if source.get("chunk_id")
        ]

        from rag.sqlite_store import KBSQLiteStore

        chunks: list[dict] = []
        if chunk_ids:
            kb_store = KBSQLiteStore(self.workspace)
            try:
                kb_store.init_db()
                rows = kb_store.get_chunks_by_ids(chunk_ids)
            finally:
                kb_store.close()
            for chunk_id in chunk_ids:
                if chunk_id not in rows:
                    continue
                chunk = dict(rows[chunk_id])
                chunk["chunk_id"] = chunk["id"]
                chunks.append(chunk)

        try:
            llm = _get_llm_provider(self.config)
        except Exception as exc:
            logger.warning("No LLM provider for wrong-answer variant: %s", exc)
            return _err("AI 模型未配置，无法生成变式题，请在设置中完成配置。", code="provider_unconfigured")

        # 回退链：优先用原文 chunk 生成变式；证据缺失（联网题、旧题、重同步后
        # chunk 失效）时按原题概念重新出题；仍失败则原题重练，避免错题永远
        # 无法进入复习。
        if chunks:
            try:
                variant = QuestionGenerator(self.workspace, llm).generate_wrong_answer_variant(
                    original,
                    entry["user_answer"],
                    chunks,
                )
                if variant:
                    variant.id = store.add_question(variant)
                    return _ok(question_id=variant.id, question=self._question_for_practice(variant), mode="variant")
            except Exception as exc:
                logger.warning("Could not generate wrong-answer variant: %s", exc)

        concepts = [name for name in (original.concepts or []) if name]
        if concepts:
            try:
                fallback = QuestionGenerator(self.workspace, llm).generate_from_query(
                    query="、".join(concepts),
                    count=1,
                )
                if fallback:
                    question = fallback[0]
                    question.id = store.add_question(question)
                    return _ok(question_id=question.id, question=self._question_for_practice(question), mode="concept_fallback")
            except Exception as exc:
                logger.warning("Could not generate concept fallback question: %s", exc)

        # 最后回退：原题重练（前端可据此标注"复习原题"）。
        return _ok(question_id=entry["question_id"], question=self._question_for_practice(original), mode="replay")

    def get_weakness_analysis(self) -> dict[str, Any]:
        from quiz.review import QuizReviewer
        store = QuizStore(self.workspace)
        reviewer = QuizReviewer(store)
        analysis = reviewer.get_weakness_analysis()
        return _ok(analysis=analysis)

    # --- Question bank (E18) ---

    _BANK_FILTER_STATES = (
        "all",
        "unanswered",
        "correct",
        "partial",
        "incorrect",
        "bookmarked",
    )

    @staticmethod
    def _bank_item_public(item: dict) -> dict[str, Any]:
        public = {
            "id": item["id"],
            "type": item["type"],
            "type_label": _TYPE_LABELS.get(item["type"], item["type"]),
            "question": item["question"],
            "options": item["options"],
            "concepts": item["concepts"],
            "difficulty": item["difficulty"],
            "source": item["source"],
            "created_at": item["created_at"],
            "state": item["state"],
            "bookmarked": item["bookmarked"],
            "bookmarked_at": item["bookmarked_at"],
            "attribution": {
                "kind": item["attribution_kind"],
                "sources": item["sources"],
            },
            "last_attempt": item["last_attempt"],
        }
        # The store only exposes the reference answer for questions the learner
        # already answered, so forwarding it cannot turn the bank into an answer
        # sheet for unanswered questions.
        if "answer" in item:
            public["answer"] = item["answer"]
            public["explanation"] = item["explanation"]
        return public

    def _normalize_bank_state(self, state: str | None) -> str:
        normalized = (state or "all").strip().lower()
        return normalized if normalized in self._BANK_FILTER_STATES else "all"

    def _bank_filters(
        self,
        *,
        state: str | None = None,
        question_id: int | None = None,
        question_ids: list[int] | None = None,
        qtype: str | None = None,
        difficulty: str | None = None,
        source: str | None = None,
        course: str | None = None,
        concept: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """The complete bank filter set, shared by list / count / practice."""
        return {
            "state": self._normalize_bank_state(state),
            "question_id": question_id,
            "question_ids": question_ids,
            "qtype": qtype,
            "difficulty": difficulty,
            "source": source,
            "course": course,
            "concept": concept,
            "query": query,
        }

    def get_bank(
        self,
        *,
        state: str | None = None,
        question_id: int | None = None,
        set_id: int | None = None,
        qtype: str | None = None,
        difficulty: str | None = None,
        source: str | None = None,
        course: str | None = None,
        concept: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        filters = self._bank_filters(
            state=state, question_id=question_id, qtype=qtype,
            difficulty=difficulty, source=source,
            course=course, concept=concept, query=query,
        )
        bounded_limit = max(1, min(int(limit or 50), 200))
        bounded_offset = max(0, int(offset or 0))
        set_name = ""
        if set_id is not None:
            record = store.get_question_set(int(set_id))
            if not record:
                return _err("练习集不存在。", code="question_set_not_found")
            set_name = record["name"]
            # An empty set must read as empty, not as "no filter" (the store
            # treats an empty id list as no constraint at all).
            if not record["question_ids"]:
                return _ok(
                    items=[], total=0, overview=store.bank_overview(),
                    state=filters["state"], limit=bounded_limit,
                    offset=bounded_offset, set_id=int(set_id), set_name=set_name,
                )
            filters["question_ids"] = record["question_ids"]
        items = store.list_bank_questions(
            **filters, limit=bounded_limit, offset=bounded_offset
        )
        return _ok(
            items=[self._bank_item_public(item) for item in items],
            total=store.count_bank_questions(**filters),
            overview=store.bank_overview(),
            state=filters["state"],
            limit=bounded_limit,
            offset=bounded_offset,
            set_id=int(set_id) if set_id is not None else None,
            set_name=set_name,
        )

    def count_bank(
        self,
        *,
        state: str | None = None,
        question_id: int | None = None,
        question_ids: list[int] | None = None,
        qtype: str | None = None,
        difficulty: str | None = None,
        source: str | None = None,
        course: str | None = None,
        concept: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Just the count, for callers that do not need the rows or the overview."""
        store = QuizStore(self.workspace)
        total = store.count_bank_questions(**self._bank_filters(
            state=state, question_id=question_id, question_ids=question_ids, qtype=qtype,
            difficulty=difficulty, source=source,
            course=course, concept=concept, query=query,
        ))
        return _ok(total=total, state=self._normalize_bank_state(state))

    def bookmark_question(self, question_id: int, bookmarked: bool = True) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        if not store.set_bookmark(question_id, bookmarked):
            return _err("题目不存在。", code="question_not_found")
        return _ok(question_id=question_id, bookmarked=bool(bookmarked))

    def start_bank_practice(
        self,
        question_ids: list[int] | None = None,
        *,
        state: str | None = None,
        qtype: str | None = None,
        difficulty: str | None = None,
        source: str | None = None,
        course: str | None = None,
        concept: str | None = None,
        query: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        ids = [int(item) for item in (question_ids or []) if int(item) > 0][:15]
        if not ids:
            # "Practice what I am looking at": the same filter set the list used,
            # so a concept / keyword / bookmark filter can be practised directly.
            filters = self._bank_filters(
                state=state, qtype=qtype, difficulty=difficulty, source=source,
                course=course, concept=concept, query=query,
            )
            ids = [
                item["id"]
                for item in store.list_bank_questions(
                    **filters,
                    limit=max(1, min(int(limit or 5), 15)),
                )
            ]
        if not ids:
            return _err("题库中没有符合条件的题目。", code="bank_empty")
        return self.start_quiz(count=len(ids), question_ids=ids, origin="practice")

    # --- Named practice sets (E18 / D2 / D8) ---

    MAX_SET_QUESTIONS = 200

    def list_question_sets(self) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        return _ok(sets=store.list_question_sets())

    def get_question_set(self, set_id: int) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        record = store.get_question_set(set_id)
        if not record:
            return _err("练习集不存在。", code="question_set_not_found")
        items = store.list_bank_questions(
            question_ids=record["question_ids"], limit=self.MAX_SET_QUESTIONS
        )
        by_id = {item["id"]: item for item in items}
        ordered = [by_id[qid] for qid in record["question_ids"] if qid in by_id]
        return _ok(
            set_id=record["id"],
            name=record["name"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            items=[self._bank_item_public(item) for item in ordered],
        )

    def create_question_set(
        self,
        name: str,
        question_ids: list[int] | None = None,
        *,
        state: str | None = None,
        concept: str | None = None,
        qtype: str | None = None,
        difficulty: str | None = None,
        source: str | None = None,
        course: str | None = None,
        query: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Create a set from explicit ids, or from whatever the bank is filtered to."""
        store = QuizStore(self.workspace)
        ids = [int(item) for item in (question_ids or []) if int(item) > 0]
        if not ids:
            ids = [
                item["id"]
                for item in store.list_bank_questions(
                    **self._bank_filters(
                        state=state, concept=concept, qtype=qtype,
                        difficulty=difficulty, source=source,
                        course=course, query=query,
                    ),
                    limit=max(1, min(int(limit or 200), self.MAX_SET_QUESTIONS)),
                )
            ]
        record = store.create_question_set(name, ids[: self.MAX_SET_QUESTIONS])
        if not record:
            return _err("练习集需要一个名字。", code="question_set_name_required")
        return _ok(
            set_id=record["id"],
            name=record["name"],
            question_ids=record["question_ids"],
            question_count=len(record["question_ids"]),
        )

    def rename_question_set(self, set_id: int, name: str) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        if not store.get_question_set(set_id):
            return _err("练习集不存在。", code="question_set_not_found")
        if not store.rename_question_set(set_id, name):
            return _err("练习集需要一个名字。", code="question_set_name_required")
        return _ok(set_id=set_id, name=(name or "").strip()[:80])

    def delete_question_set(self, set_id: int) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        if not store.delete_question_set(set_id):
            return _err("练习集不存在。", code="question_set_not_found")
        return _ok(set_id=set_id, deleted=True)

    def add_question_to_set(self, set_id: int, question_id: int) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        if not store.get_question_set(set_id):
            return _err("练习集不存在。", code="question_set_not_found")
        if not store.add_question_to_set(set_id, question_id):
            return _err("题目不存在。", code="question_not_found")
        return _ok(set_id=set_id, question_id=question_id)

    def remove_question_from_set(self, set_id: int, question_id: int) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        if not store.get_question_set(set_id):
            return _err("练习集不存在。", code="question_set_not_found")
        store.remove_question_from_set(set_id, question_id)
        return _ok(set_id=set_id, question_id=question_id, removed=True)

    def start_set_practice(self, set_id: int, limit: int = 15) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        record = store.get_question_set(set_id)
        if not record:
            return _err("练习集不存在。", code="question_set_not_found")
        ids = record["question_ids"][: max(1, min(int(limit or 15), 15))]
        if not ids:
            return _err("这个练习集里还没有题目。", code="question_set_empty")
        return self.start_quiz(count=len(ids), question_ids=ids, origin="practice")

    # --- Stats ---

    def get_stats(self) -> dict[str, Any]:
        store = QuizStore(self.workspace)
        counts = store.count_questions()
        if not counts:
            return _ok(total=0, counts={})
        return _ok(total=sum(counts.values()), counts=counts)
