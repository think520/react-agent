"""LearningService — business logic for learning plans, progress, and reviews.

Used by both cli/repl.py and tools/learning_tools.py.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import logging
from typing import Any

from learning.store import LearningStore
from learning.scheduler import ReviewScheduler
from learning.schema import MASTERY_LEARNING, MASTERY_MASTERED, MASTERY_NEEDS_REVIEW
from learning.progress import ProgressTracker
from learning.path import LearningPathGenerator
from learning.workflow import PlanWorkflowTracker
from service._result import err as _err, ok as _ok

logger = logging.getLogger(__name__)


def _get_llm_provider(config: dict | None = None):
    from service.runtime_service import RuntimeService
    if config is None:
        config = RuntimeService.load_default_config()
    return RuntimeService.create_provider(config)


class LearningService:
    """Stateless service: each method creates its own store/scheduler instances."""

    def __init__(self, workspace: str = ".", config: dict | None = None):
        self.workspace = workspace
        self.config = config

    # --- Plan generation ---

    def generate_path(
        self,
        goal: str,
        course: str | None = None,
        deadline: str | None = None,
    ) -> dict[str, Any]:
        store = LearningStore(self.workspace)
        progress = ProgressTracker(store, ReviewScheduler(store))
        try:
            llm = _get_llm_provider(self.config)
        except Exception:
            llm = None

        generator = LearningPathGenerator(store, progress, llm)
        plan = generator.generate_path(
            goal=goal, course=course, deadline=deadline, workspace=self.workspace,
        )
        if not plan.steps:
            return _err("未能生成学习计划。请确保知识库中有相关资料。")

        steps = []
        for step in plan.steps:
            steps.append({
                "day": step.get("day", "?"),
                "topics": step.get("topics", []),
                "tasks": step.get("tasks", []),
                "review": step.get("review", []),
            })

        return _ok(
            plan_id=plan.id,
            title=plan.title,
            total_days=len(plan.steps),
            course=plan.course,
            deadline=plan.deadline,
            steps=steps,
        )

    # --- Progress ---

    def get_progress(self, concept: str | None = None) -> dict[str, Any]:
        store = LearningStore(self.workspace)
        scheduler = ReviewScheduler(store)
        progress = ProgressTracker(store, scheduler)

        if concept:
            detail = progress.get_concept_detail(concept)
            if not detail:
                return _err(f"未找到知识点 '{concept}' 的掌握度记录。")
            return _ok(**detail)

        overview = progress.get_overview()
        return _ok(**overview)

    # --- Reviews ---

    def get_due_reviews(self, limit: int = 20) -> dict[str, Any]:
        store = LearningStore(self.workspace)
        scheduler = ReviewScheduler(store)
        due = scheduler.get_due_concepts(limit=limit)
        concepts = []
        for m in due:
            concepts.append({
                "concept": m.concept,
                "status": m.status,
                "score": m.score,
                "consecutive_correct": m.consecutive_correct,
            })
        return _ok(count=len(due), concepts=concepts)

    # --- W1 E6：掌握度引擎接线 ---

    ATTEMPT_WINDOW = 5

    def _derived_mastery(self, record: dict[str, Any], store: LearningStore) -> dict[str, Any]:
        """给队列条目补上「推导出来的掌握度」。

        - 有逐次历史 → 用纯函数引擎算（并给出证据条数）；
        - 老数据没有历史 → 退回存量 score，但**如实标注** «mastery_source="stored"»，
          不把存量冒充推导结果。
        """
        from learning.engine import weighted_mastery

        concept = str(record.get("concept") or "")
        history = store.recent_mastery_attempts(concept, limit=self.ATTEMPT_WINDOW) if concept else []
        if history:
            return {
                **record,
                "mastery": weighted_mastery(history),
                "evidence": len(history),
                "mastery_source": "history",
            }
        return {
            **record,
            "mastery": round(float(record.get("score") or 0.0), 4),
            "evidence": 0,
            "mastery_source": "stored",
        }

    def mastery_overview(self, limit: int = 5) -> dict[str, Any]:
        """掌握度总览（W1 E6）：最弱的几个概念 + **推导**分数，并标注来源。

        «list_mastery» 按分数升序 —— 最需要推进的排在最前面。
        """
        store = LearningStore(self.workspace)
        rows = store.list_mastery(limit=max(1, int(limit)))
        return _ok(overview=[
            self._derived_mastery({"concept": row.concept, "score": row.score, "status": row.status}, store)
            for row in rows
        ])

    def get_next_objective(self) -> dict[str, Any] | None:
        """今天下一件该做的事（纯函数引擎给优先级）。

        挂起问题 > 到期复习 > 第一个未掌握点；都没有就返回 None（今天没有必须做的）。
        """
        from learning.engine import next_objective
        from service.interaction_service import InteractionService

        pending = InteractionService(self.workspace).list_pending(limit=1)
        pending_payload: dict[str, Any] | None = None
        if pending:
            questions = pending[0].get("questions") or []
            prompt = str(questions[0].get("prompt") or "") if questions else ""
            pending_payload = {
                "interaction_id": pending[0].get("interaction_id", ""),
                "prompt": prompt,
            }
        store = LearningStore(self.workspace)
        unmastered = [
            row.concept for row in store.list_mastery(limit=50) if row.status != MASTERY_MASTERED
        ]
        return next_objective(
            pending_question=pending_payload,
            due_reviews=self.get_due_reviews(limit=1).get("concepts", []),
            unseen_concepts=unmastered,
        )

    # D5: the wrong set belongs to the bank, not to a 20-row window. The rows
    # stay bounded so a long history cannot flood the page, but the reported
    # total comes from the bank, so Review and the bank always agree.
    WRONG_ANSWER_LIMIT = 200

    def get_review_queue(
        self, limit: int = 20, wrong_limit: int | None = None
    ) -> dict[str, Any]:
        due_result = self.get_due_reviews(limit=limit)
        from quiz.store import QuizStore
        from service.quiz_service import QuizService
        quiz_store = QuizStore(self.workspace)
        quiz_service = QuizService(self.workspace, config=self.config)
        learning_store = LearningStore(self.workspace)
        bounded_wrong = max(1, min(int(wrong_limit or self.WRONG_ANSWER_LIMIT), 500))
        wrong_result = quiz_service.get_wrong_answer_book(limit=bounded_wrong)
        wrong_total = quiz_service.count_bank(state="incorrect").get("total", 0)
        weakness_result = quiz_service.get_weakness_analysis()
        # W1 E9：带上"最近一次答错是哪次"，让界面能走 E3 已交付的**变式**通道，
        # 而不是把原题重放一遍（变式通道只认 attempt_id）。
        due_concepts = [
            self._derived_mastery({
                **record,
                "question_ids": quiz_store.find_question_ids_by_concept(record["concept"]),
                "last_attempt_id": quiz_store.last_wrong_attempt_id_for_concept(record["concept"]),
            }, learning_store)
            for record in due_result.get("concepts", [])
        ]
        weaknesses = [
            self._derived_mastery({
                **record,
                "question_ids": quiz_store.find_question_ids_by_concept(record["concept"]),
                "last_attempt_id": quiz_store.last_wrong_attempt_id_for_concept(record["concept"]),
            }, learning_store)
            for record in weakness_result.get("analysis", [])
        ]
        next_review = learning_store.get_next_scheduled_review()
        return _ok(
            due_concepts=due_concepts,
            wrong_answers=wrong_result.get("entries", []),
            wrong_total=wrong_total,
            weaknesses=weaknesses,
            next_review=(
                {
                    "concept": next_review.concept,
                    "status": next_review.status,
                    "next_review": next_review.next_review,
                }
                if next_review else None
            ),
            # W1 E6 接线：今天下一件该做的事（挂起问题 > 到期复习 > 第一个未掌握点）。
            next_objective=self.get_next_objective(),
        )

    # --- Manual mastery ---

    _VALID_STATUSES = {MASTERY_MASTERED, MASTERY_LEARNING, MASTERY_NEEDS_REVIEW}

    def mark_mastery(self, concept: str, status: str) -> dict[str, Any]:
        if status not in self._VALID_STATUSES:
            return _err(f"Invalid status: {status}. Use: {', '.join(sorted(self._VALID_STATUSES))}")
        store = LearningStore(self.workspace)
        scheduler = ReviewScheduler(store)
        m = scheduler.mark_manual(concept, status)
        return _ok(
            concept=m.concept,
            status=m.status,
            score=m.score,
        )

    # --- Plans ---

    def list_plans(self, limit: int = 10) -> dict[str, Any]:
        store = LearningStore(self.workspace)
        plans = store.list_plans(limit=limit)
        result = []
        for p in plans:
            result.append({
                "id": p.id,
                "title": p.title,
                "days": len(p.steps),
                "course": p.course,
                "deadline": p.deadline,
                "status": p.status,
            })
        return _ok(plans=result)

    # --- Today tasks (catch-up mode) ---

    def get_today_tasks(self) -> dict[str, Any]:
        store = LearningStore(self.workspace)
        tracker = PlanWorkflowTracker(store)
        today = tracker.get_today_tasks(self.workspace)
        return _ok(**today)

    # --- Plan progress ---

    def get_plan_progress(self, plan_id: int) -> dict[str, Any]:
        store = LearningStore(self.workspace)
        tracker = PlanWorkflowTracker(store)
        summary = tracker.get_plan_progress_summary(plan_id)
        if not summary:
            return _err(f"未找到计划 #{plan_id}。")
        return _ok(**summary)

    def complete_task(self, plan_id: int, day: int, task_index: int) -> dict[str, Any]:
        store = LearningStore(self.workspace)
        plan = store.get_plan(plan_id)
        if not plan:
            return _err(f"未找到计划 #{plan_id}。")

        target_tasks = []
        for step in plan.steps:
            if step.get("day") == day:
                target_tasks = step.get("tasks", [])
                break
        if not target_tasks:
            return _err(f"计划 #{plan_id} 没有第 {day} 天的任务。")
        if task_index < 0 or task_index >= len(target_tasks):
            return _err(f"第 {day} 天只有 {len(target_tasks)} 个任务，task_index={task_index} 越界。")

        store.mark_task_done(plan_id, day, task_index, source="manual")

        tracker = PlanWorkflowTracker(store)
        progress = store.get_progress(plan_id)
        if tracker._all_steps_done(plan, progress):
            store.update_plan_status(plan_id, status="completed")

        return _ok(message=f"已标记计划 #{plan_id} 第 {day} 天第 {task_index + 1} 个任务完成。")

    def complete_step(self, plan_id: int, day: int) -> dict[str, Any]:
        store = LearningStore(self.workspace)
        plan = store.get_plan(plan_id)
        if not plan:
            return _err(f"未找到计划 #{plan_id}。")

        tasks = []
        for step in plan.steps:
            if step.get("day") == day:
                tasks = step.get("tasks", [])
                break
        if not tasks:
            return _err(f"计划 #{plan_id} 没有第 {day} 天的任务。")

        store.mark_step_done(plan_id, day, len(tasks), source="manual")

        tracker = PlanWorkflowTracker(store)
        progress = store.get_progress(plan_id)
        if tracker._all_steps_done(plan, progress):
            store.update_plan_status(plan_id, status="completed")

        return _ok(message=f"已标记计划 #{plan_id} 第 {day} 天全部完成。")
