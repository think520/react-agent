import json
import logging

from .base import register_tool, ToolResult

logger = logging.getLogger(__name__)


def learning_path(
    goal: str,
    course: str | None = None,
    deadline: str | None = None,
    workspace: str = ".",
) -> ToolResult:
    """Generate a personalized learning plan based on goal, mastery state, and course materials."""
    try:
        from service.learning_service import LearningService
        svc = LearningService(workspace)
        result = svc.generate_path(goal=goal, course=course, deadline=deadline)

        if not result["ok"]:
            return ToolResult(ok=False, content=result["error"])

        lines = [f"学习计划: {result['title']}\n"]
        for step in result["steps"]:
            day = step["day"]
            topics = ", ".join(step["topics"])
            tasks = step["tasks"]
            lines.append(f"第 {day} 天: {topics}")
            for t in tasks:
                lines.append(f"  - {t}")
            if step.get("review"):
                lines.append(f"  复习: {', '.join(step['review'])}")
            lines.append("")

        data = {
            "plan_id": result["plan_id"],
            "title": result["title"],
            "total_days": result["total_days"],
            "course": result["course"],
            "deadline": result["deadline"],
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
        from service.learning_service import LearningService
        svc = LearningService(workspace)
        result = svc.get_progress(concept=concept)

        if not result["ok"]:
            return ToolResult(ok=False, content=result["error"])

        if concept:
            lines = [
                f"知识点: {result['concept']}",
                f"状态: {result['status']}",
                f"掌握度: {result['score']:.0%}",
                f"复习次数: {result['review_count']}",
                f"连续正确: {result['consecutive_correct']}",
                f"来源: {result['source']}",
            ]
            if result.get("next_review"):
                lines.append(f"下次复习: {result['next_review'][:16]}")
            return ToolResult(ok=True, content="\n".join(lines), data=result)

        if result["total_concepts"] == 0:
            return ToolResult(ok=True, content="暂无学习进度记录。开始做题后会自动追踪掌握度。", data=result)

        lines = [
            f"学习进度概览",
            f"已跟踪知识点: {result['total_concepts']}",
            f"平均掌握度: {result['average_score']:.0%}",
            f"状态分布: {json.dumps(result['by_status'], ensure_ascii=False)}",
        ]

        if result.get("weakest"):
            lines.append("\n最薄弱知识点:")
            for w in result["weakest"]:
                lines.append(f"  - {w['concept']}: {w['score']:.0%} ({w['status']})")

        if result.get("strongest"):
            lines.append("\n掌握最好:")
            for s in result["strongest"]:
                lines.append(f"  - {s['concept']}: {s['score']:.0%} ({s['status']})")

        return ToolResult(ok=True, content="\n".join(lines), data=result)
    except Exception as e:
        logger.error("Learning progress failed: %s", e)
        return ToolResult(ok=False, content=f"查询学习进度失败: {e}")


def learning_review(
    workspace: str = ".",
) -> ToolResult:
    """Get concepts due for review today."""
    try:
        from service.learning_service import LearningService
        svc = LearningService(workspace)
        result = svc.get_due_reviews()

        if result["count"] == 0:
            return ToolResult(ok=True, content="今天没有需要复习的知识点！", data={"due_count": 0})

        lines = [f"今日复习清单 ({result['count']} 个知识点):\n"]
        for i, r in enumerate(result["concepts"], 1):
            lines.append(f"{i}. {r['concept']} — 掌握度 {r['score']:.0%}, 连续正确 {r['consecutive_correct']}")

        lines.append("\n使用 quiz_start 开始针对性练习。")
        return ToolResult(ok=True, content="\n".join(lines), data={"due_count": result["count"], "concepts": [r["concept"] for r in result["concepts"]]})
    except Exception as e:
        logger.error("Learning review failed: %s", e)
        return ToolResult(ok=False, content=f"获取复习清单失败: {e}")


def learning_plan_progress(
    plan_id: int | None = None,
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
        from service.learning_service import LearningService
        svc = LearningService(workspace)

        if action == "today":
            result = svc.get_today_tasks()
            today = {k: v for k, v in result.items() if k != "ok"}

            if not today["plans"] and not today["reviews"]:
                return ToolResult(ok=True, content="没有待完成的学习任务或复习。", data=today)

            lines = []
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

        # Actions below require plan_id
        if plan_id is None:
            return ToolResult(ok=False, content=f"action='{action}' 需要 plan_id 参数。")

        if action == "status":
            result = svc.get_plan_progress(plan_id)
            if not result["ok"]:
                return ToolResult(ok=False, content=result["error"])

            summary = {k: v for k, v in result.items() if k != "ok"}
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
            result = svc.complete_task(plan_id, day, task_index)
            if not result["ok"]:
                return ToolResult(ok=False, content=result["error"])
            return ToolResult(ok=True, content=result["message"])

        if action == "complete_step":
            if day is None:
                return ToolResult(ok=False, content="complete_step 需要 day 参数。")
            result = svc.complete_step(plan_id, day)
            if not result["ok"]:
                return ToolResult(ok=False, content=result["error"])
            return ToolResult(ok=True, content=result["message"])

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
        "'complete_step' to mark a whole day done, 'today' to see all pending tasks + due reviews. "
        "plan_id is required for status/complete_task/complete_step but not for 'today'."
    ),
    params_schema={
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer", "description": "The learning plan ID (required for status/complete_task/complete_step)"},
            "action": {
                "type": "string",
                "enum": ["status", "complete_task", "complete_step", "today"],
                "description": "Action to perform (default: status)",
            },
            "day": {"type": "integer", "description": "Day number (for complete_task/complete_step)"},
            "task_index": {"type": "integer", "description": "Task index within the day, 0-based (for complete_task)"},
        },
        "required": [],
    },
    func=learning_plan_progress,
)
