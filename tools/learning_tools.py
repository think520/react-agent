import json
import logging

from learning.store import LearningStore
from learning.scheduler import ReviewScheduler
from learning.progress import ProgressTracker
from learning.path import LearningPathGenerator

from .base import register_tool, ToolResult

logger = logging.getLogger(__name__)


def _get_llm_provider():
    from providers.factory import ProviderFactory
    return ProviderFactory.create_from_config()


def learning_path(
    goal: str,
    course: str | None = None,
    deadline: str | None = None,
    workspace: str = ".",
) -> ToolResult:
    """Generate a personalized learning plan based on goal, mastery state, and course materials."""
    try:
        store = LearningStore(workspace)
        progress = ProgressTracker(store, ReviewScheduler(store))

        try:
            llm = _get_llm_provider()
        except Exception:
            llm = None

        generator = LearningPathGenerator(store, progress, llm)
        plan = generator.generate_path(goal=goal, course=course, deadline=deadline, workspace=workspace)

        if not plan.steps:
            return ToolResult(ok=False, content="未能生成学习计划。请确保知识库中有相关资料。")

        lines = [f"学习计划: {plan.title}\n"]
        for step in plan.steps:
            day = step.get("day", "?")
            topics = ", ".join(step.get("topics", []))
            tasks = step.get("tasks", [])
            lines.append(f"第 {day} 天: {topics}")
            for t in tasks:
                lines.append(f"  - {t}")
            if step.get("review"):
                lines.append(f"  复习: {', '.join(step['review'])}")
            lines.append("")

        data = {
            "plan_id": plan.id,
            "title": plan.title,
            "total_days": len(plan.steps),
            "course": plan.course,
            "deadline": plan.deadline,
        }

        return ToolResult(ok=True, content="\n".join(lines), data=data)
    except Exception as e:
        logger.error("Learning path generation failed: %s", e)
        return ToolResult(ok=False, content=f"学习计划生成失败: {e}")


def learning_progress(
    concept: str | None = None,
    course: str | None = None,
    workspace: str = ".",
) -> ToolResult:
    """Show learning progress: overall mastery overview or details for a specific concept."""
    try:
        store = LearningStore(workspace)
        scheduler = ReviewScheduler(store)
        progress = ProgressTracker(store, scheduler)

        if concept:
            detail = progress.get_concept_detail(concept)
            if not detail:
                return ToolResult(ok=False, content=f"未找到知识点 '{concept}' 的掌握度记录。")

            lines = [
                f"知识点: {detail['concept']}",
                f"状态: {detail['status']}",
                f"掌握度: {detail['score']:.0%}",
                f"复习次数: {detail['review_count']}",
                f"连续正确: {detail['consecutive_correct']}",
                f"来源: {detail['source']}",
            ]
            if detail["next_review"]:
                lines.append(f"下次复习: {detail['next_review'][:16]}")
            return ToolResult(ok=True, content="\n".join(lines), data=detail)

        overview = progress.get_overview()
        if overview["total_concepts"] == 0:
            return ToolResult(ok=True, content="暂无学习进度记录。开始做题后会自动追踪掌握度。", data=overview)

        lines = [
            f"学习进度概览",
            f"已跟踪知识点: {overview['total_concepts']}",
            f"平均掌握度: {overview['average_score']:.0%}",
            f"状态分布: {json.dumps(overview['by_status'], ensure_ascii=False)}",
        ]

        if overview["weakest"]:
            lines.append("\n最薄弱知识点:")
            for w in overview["weakest"]:
                lines.append(f"  - {w['concept']}: {w['score']:.0%} ({w['status']})")

        if overview["strongest"]:
            lines.append("\n掌握最好:")
            for s in overview["strongest"]:
                lines.append(f"  - {s['concept']}: {s['score']:.0%} ({s['status']})")

        return ToolResult(ok=True, content="\n".join(lines), data=overview)
    except Exception as e:
        logger.error("Learning progress failed: %s", e)
        return ToolResult(ok=False, content=f"查询学习进度失败: {e}")


def learning_review(
    workspace: str = ".",
) -> ToolResult:
    """Get concepts due for review today."""
    try:
        store = LearningStore(workspace)
        scheduler = ReviewScheduler(store)
        due = scheduler.get_due_concepts(limit=20)

        if not due:
            return ToolResult(ok=True, content="今天没有需要复习的知识点！", data={"due_count": 0})

        lines = [f"今日复习清单 ({len(due)} 个知识点):\n"]
        for i, m in enumerate(due, 1):
            lines.append(f"{i}. {m.concept} — 掌握度 {m.score:.0%}, 连续正确 {m.consecutive_correct}")

        lines.append("\n使用 quiz_start 开始针对性练习。")
        return ToolResult(ok=True, content="\n".join(lines), data={"due_count": len(due), "concepts": [m.concept for m in due]})
    except Exception as e:
        logger.error("Learning review failed: %s", e)
        return ToolResult(ok=False, content=f"获取复习清单失败: {e}")


def learning_plan_progress(
    plan_id: int,
    action: str = "status",
    day: int | None = None,
    task_index: int | None = None,
    workspace: str = ".",
) -> ToolResult:
    """Manage learning plan execution progress.

    Actions:
      - status: show plan progress summary
      - complete_task: mark a specific task done (requires day + task_index)
      - complete_step: mark all tasks in a day done (requires day)
      - today: show today's tasks + due reviews (catch-up mode)
    """
    try:
        from learning.workflow import PlanWorkflowTracker

        store = LearningStore(workspace)
        tracker = PlanWorkflowTracker(store)

        if action == "today":
            today = tracker.get_today_tasks(workspace)
            lines = []

            if not today["plans"] and not today["reviews"]:
                return ToolResult(ok=True, content="没有待完成的学习任务或复习。", data=today)

            for p in today["plans"]:
                lines.append(f"学习计划: {p['title']}")
                if p.get("deadline"):
                    lines.append(f"  截止: {p['deadline']}")
                for step in p["steps"]:
                    topics = ", ".join(step["topics"])
                    lines.append(f"  第 {step['day']} 天: {topics}")
                    for task in step["tasks"]:
                        lines.append(f"    [ ] {task}")
                lines.append("")

            if today["reviews"]:
                lines.append(f"复习清单 ({len(today['reviews'])} 个知识点):")
                for i, r in enumerate(today["reviews"], 1):
                    lines.append(f"  {i}. {r['concept']} — 掌握度 {r['score']:.0%} ({r['status']})")

            return ToolResult(ok=True, content="\n".join(lines), data=today)

        if action == "status":
            summary = tracker.get_plan_progress_summary(plan_id)
            if not summary:
                return ToolResult(ok=False, content=f"未找到计划 #{plan_id}。")

            lines = [
                f"计划: {summary['title']}",
                f"状态: {summary['status']}",
                f"进度: {summary['done_tasks']}/{summary['total_tasks']} ({summary['progress_pct']}%)",
            ]
            for step in summary["steps"]:
                status_icon = "✓" if step["all_done"] else "○"
                topics = ", ".join(step["topics"])
                lines.append(f"  {status_icon} 第 {step['day']} 天: {topics}")
                for t in step["tasks"]:
                    task_icon = "✓" if t["done"] else " "
                    lines.append(f"    [{task_icon}] {t['text']}")

            return ToolResult(ok=True, content="\n".join(lines), data=summary)

        if action == "complete_task":
            if day is None or task_index is None:
                return ToolResult(ok=False, content="complete_task 需要 day 和 task_index 参数。")
            store.mark_task_done(plan_id, day, task_index, source="manual")
            return ToolResult(ok=True, content=f"已标记计划 #{plan_id} 第 {day} 天第 {task_index + 1} 个任务完成。")

        if action == "complete_step":
            if day is None:
                return ToolResult(ok=False, content="complete_step 需要 day 参数。")
            plan = store.get_plan(plan_id)
            if not plan:
                return ToolResult(ok=False, content=f"未找到计划 #{plan_id}。")
            tasks = []
            for step in plan.steps:
                if step.get("day") == day:
                    tasks = step.get("tasks", [])
                    break
            if not tasks:
                return ToolResult(ok=False, content=f"计划 #{plan_id} 没有第 {day} 天的任务。")
            store.mark_step_done(plan_id, day, len(tasks), source="manual")

            # Check if plan is now fully complete
            progress = store.get_progress(plan_id)
            tracker_check = PlanWorkflowTracker(store)
            if tracker_check._all_steps_done(plan, progress):
                store.update_plan_status(plan_id, status="completed")

            return ToolResult(ok=True, content=f"已标记计划 #{plan_id} 第 {day} 天全部完成。")

        return ToolResult(ok=False, content=f"未知 action: {action}。支持: status, complete_task, complete_step, today")

    except Exception as e:
        logger.error("Learning plan progress failed: %s", e)
        return ToolResult(ok=False, content=f"计划进度操作失败: {e}")


# Register tools
register_tool(
    name="learning_path",
    description="Generate a personalized learning plan based on a goal, course materials, and mastery data. Use when the user wants a study plan or learning roadmap.",
    params_schema={
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Learning goal, e.g. '复习操作系统期末考试'"},
            "course": {"type": "string", "description": "Optional course name to focus on"},
            "deadline": {"type": "string", "description": "Optional deadline, e.g. '2026-06-20'"},
        },
        "required": ["goal"],
    },
    func=learning_path,
)

register_tool(
    name="learning_progress",
    description="Show learning progress and mastery overview. Can show overall stats or details for a specific concept.",
    params_schema={
        "type": "object",
        "properties": {
            "concept": {"type": "string", "description": "Optional specific concept to check mastery for"},
            "course": {"type": "string", "description": "Optional course filter"},
        },
        "required": [],
    },
    func=learning_progress,
)

register_tool(
    name="learning_review",
    description="Get the list of concepts due for review today based on spaced repetition schedule.",
    params_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
    func=learning_review,
)

register_tool(
    name="learning_plan_progress",
    description=(
        "Manage learning plan execution progress. "
        "Use 'status' to view progress, 'complete_task' to mark a single task done, "
        "'complete_step' to mark a whole day done, 'today' to see all pending tasks + due reviews."
    ),
    params_schema={
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer", "description": "The learning plan ID"},
            "action": {
                "type": "string",
                "enum": ["status", "complete_task", "complete_step", "today"],
                "description": "Action to perform (default: status)",
            },
            "day": {"type": "integer", "description": "Day number (for complete_task/complete_step)"},
            "task_index": {"type": "integer", "description": "Task index within the day, 0-based (for complete_task)"},
        },
        "required": ["plan_id"],
    },
    func=learning_plan_progress,
)
