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

    def get_review_queue(self, limit: int = 20) -> dict[str, Any]:
        due_result = self.get_due_reviews(limit=limit)
        from quiz.store import QuizStore
        from service.quiz_service import QuizService
        quiz_store = QuizStore(self.workspace)
        quiz_service = QuizService(self.workspace, config=self.config)
        wrong_result = quiz_service.get_wrong_answer_book(limit=limit)
        weakness_result = quiz_service.get_weakness_analysis()
        due_concepts = [
            {
                **record,
                "question_ids": quiz_store.find_question_ids_by_concept(record["concept"]),
            }
            for record in due_result.get("concepts", [])
        ]
        weaknesses = [
            {
                **record,
                "question_ids": quiz_store.find_question_ids_by_concept(record["concept"]),
            }
            for record in weakness_result.get("analysis", [])
        ]
        return _ok(
            due_concepts=due_concepts,
            wrong_answers=wrong_result.get("entries", []),
            weaknesses=weaknesses,
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
