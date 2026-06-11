"""Plan workflow tracker — auto-infer step completion from mastery, query progress."""

import logging
from datetime import datetime, timezone

from .schema import LearningPlan, Mastery
from .store import LearningStore

logger = logging.getLogger(__name__)


class PlanWorkflowTracker:
    """Tracks learning plan execution progress.

    Auto-infers step completion: when all topics in a step are mastered,
    the step is automatically marked complete.
    """

    def __init__(self, store: LearningStore):
        self.store = store

    def check_plan_completion(self) -> list[dict]:
        """Check all active plans and auto-mark completed steps.

        Returns list of {plan_id, step_day, topics} for newly auto-completed steps.
        """
        results = []
        plans = self.store.get_active_plans()

        for plan in plans:
            if not plan.id:
                continue
            progress = self.store.get_progress(plan.id)
            newly_completed = self._auto_complete_steps(plan, progress)
            results.extend(newly_completed)

            # Re-read progress after auto-completion
            if newly_completed:
                progress = self.store.get_progress(plan.id)

            # Check if all steps are done → mark plan completed
            if self._all_steps_done(plan, progress):
                self.store.update_plan_status(plan.id, status="completed")
                logger.info("[Workflow] plan %d completed: %s", plan.id, plan.title)

        return results

    def _auto_complete_steps(self, plan: LearningPlan, progress: dict) -> list[dict]:
        """Auto-mark steps where all topics are mastered."""
        newly_completed = []

        for step in plan.steps:
            day = step.get("day")
            if day is None:
                continue

            tasks = step.get("tasks", [])
            if not tasks:
                continue

            # Check if all tasks already marked
            all_done = all(
                (day, i) in progress for i in range(len(tasks))
            )
            if all_done:
                continue

            # Check if all topics are mastered
            topics = step.get("topics", [])
            if not topics:
                continue

            all_mastered = all(
                self._is_topic_mastered(topic) for topic in topics
            )
            if not all_mastered:
                continue

            # Auto-mark all tasks in this step
            self.store.mark_step_done(plan.id, day, len(tasks), source="auto")
            newly_completed.append({
                "plan_id": plan.id,
                "step_day": day,
                "topics": topics,
            })
            logger.info(
                "[Workflow] auto-completed step %d of plan %d: %s",
                day, plan.id, ", ".join(topics),
            )

        return newly_completed

    def _is_topic_mastered(self, topic: str) -> bool:
        """Check if a topic's mastery status is 'mastered'."""
        m = self.store.get_mastery(topic)
        return m is not None and m.status == "mastered"

    def _all_steps_done(self, plan: LearningPlan, progress: dict) -> bool:
        """Check if every task in every step is completed.

        Returns False if the plan has no trackable tasks (empty steps or
        missing tasks) — such plans should not be auto-completed.
        """
        has_any_task = False
        for step in plan.steps:
            day = step.get("day")
            tasks = step.get("tasks", [])
            if day is None or not tasks:
                continue
            has_any_task = True
            for i in range(len(tasks)):
                if (day, i) not in progress:
                    return False
        return has_any_task

    def get_plan_progress_summary(self, plan_id: int) -> dict | None:
        """Get progress summary for a plan."""
        plan = self.store.get_plan(plan_id)
        if not plan:
            return None

        progress = self.store.get_progress(plan_id)
        total_tasks = 0
        done_tasks = 0
        steps_summary = []

        for step in plan.steps:
            day = step.get("day", 0)
            tasks = step.get("tasks", [])
            topics = step.get("topics", [])
            task_details = []

            for i, task in enumerate(tasks):
                total_tasks += 1
                is_done = (day, i) in progress
                if is_done:
                    done_tasks += 1
                task_details.append({
                    "index": i,
                    "text": task,
                    "done": is_done,
                    "source": progress[(day, i)]["source"] if is_done else None,
                })

            step_done = all((day, i) in progress for i in range(len(tasks)))
            steps_summary.append({
                "day": day,
                "topics": topics,
                "tasks": task_details,
                "all_done": step_done,
            })

        return {
            "plan_id": plan.id,
            "title": plan.title,
            "status": plan.status,
            "total_tasks": total_tasks,
            "done_tasks": done_tasks,
            "progress_pct": round(done_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            "steps": steps_summary,
        }

    def get_today_tasks(self, workspace: str = ".") -> dict:
        """Get merged view: incomplete plan tasks + due reviews (catch-up mode)."""
        result = {
            "plans": [],
            "reviews": [],
        }

        # Active plans — show ALL incomplete tasks (catch-up mode)
        plans = self.store.get_active_plans()
        for plan in plans:
            if not plan.id:
                continue
            progress = self.store.get_progress(plan.id)
            incomplete_steps = []

            for step in plan.steps:
                day = step.get("day", 0)
                tasks = step.get("tasks", [])
                topics = step.get("topics", [])
                incomplete_tasks = []

                for i, task in enumerate(tasks):
                    if (day, i) not in progress:
                        incomplete_tasks.append(task)

                if incomplete_tasks:
                    incomplete_steps.append({
                        "day": day,
                        "topics": topics,
                        "tasks": incomplete_tasks,
                    })

            if incomplete_steps:
                result["plans"].append({
                    "plan_id": plan.id,
                    "title": plan.title,
                    "deadline": plan.deadline,
                    "steps": incomplete_steps,
                })

        # Due reviews
        try:
            from .scheduler import ReviewScheduler
            scheduler = ReviewScheduler(self.store)
            due = scheduler.get_due_concepts(limit=20)
            result["reviews"] = [
                {"concept": m.concept, "score": round(m.score, 2), "status": m.status}
                for m in due
            ]
        except Exception:
            pass

        return result
