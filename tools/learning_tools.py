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
