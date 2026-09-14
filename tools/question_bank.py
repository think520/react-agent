"""Agent tools for the question bank (E18).

The bank is the one shelf holding every generated question. Per D4 the agent may
read it and mark questions, but it must not restructure it: categories, practice
sets and status changes go through the UI. The store only exposes a reference
answer for questions the learner already answered, so listing the bank can never
pre-answer a question the user has not met yet.
"""

import logging
from typing import Any

from .base import ToolResult, register_tool

logger = logging.getLogger(__name__)

_STATE_LABELS = {
    "unanswered": "未作答",
    "correct": "答对",
    "partial": "基本正确",
    "incorrect": "答错",
}


def _state_label(state: str) -> str:
    return _STATE_LABELS.get(state, state)


def _question_line(item: dict[str, Any]) -> str:
    marks = [_state_label(item.get("state", ""))]
    if item.get("bookmarked"):
        marks.append("已收藏")
    concepts = "、".join(item.get("concepts") or [])
    scope = f"｜{concepts}" if concepts else ""
    line = (
        f"- #{item['id']} [{item.get('type_label') or item.get('type')}]"
        f" {'｜'.join(marks)}{scope}：{item['question']}"
    )
    # Only answered questions carry this key; the store strips it otherwise.
    if item.get("answer"):
        line += f"\n  参考作答：{item['answer']}"
    return line


def bank_overview(workspace: str = ".") -> ToolResult:
    """Summarize the question bank: totals, per-state counts and top concepts."""
    try:
        from service.quiz_service import QuizService

        result = QuizService(workspace).get_bank(limit=1)
        if not result.get("ok"):
            return ToolResult(ok=False, content=result.get("error", "题库读取失败。"))
        overview = result["overview"]
        concepts = "、".join(
            f"{entry['concept']}（{entry['count']}）"
            for entry in overview.get("by_concept", [])[:8]
        )
        content = "\n".join([
            f"题库共 {overview['total']} 道题。",
            "状态：未作答 {unanswered}｜答对 {correct}｜基本正确 {partial}"
            "｜答错 {incorrect}｜已收藏 {bookmarked}".format(**overview),
            f"知识点分布：{concepts or '暂无'}",
        ])
        return ToolResult(ok=True, content=content, data=overview)
    except Exception as exc:
        logger.error("bank_overview failed: %s", exc)
        return ToolResult(ok=False, content=f"题库概览读取失败: {exc}")


def bank_list(
    state: str = "all",
    question_id: int | None = None,
    concept: str | None = None,
    course: str | None = None,
    difficulty: str | None = None,
    source: str | None = None,
    question_type: str | None = None,
    limit: int = 20,
    workspace: str = ".",
) -> ToolResult:
    """List bank questions, or look up the one question the user referred to."""
    try:
        from service.quiz_service import QuizService

        bounded = max(1, min(int(limit or 20), 100))
        result = QuizService(workspace).get_bank(
            state=state,
            question_id=question_id,
            concept=concept,
            course=course,
            difficulty=difficulty,
            source=source,
            qtype=question_type,
            limit=bounded,
        )
        if not result.get("ok"):
            return ToolResult(ok=False, content=result.get("error", "题库读取失败。"))
        items = result["items"]
        if not items:
            return ToolResult(
                ok=True,
                content=(f"题库中没有编号为 {question_id} 的题目。" if question_id
                         else "题库中没有符合条件的题目。"),
                data={"total": 0, "state": result["state"], "items": []},
            )
        if question_id:
            lines = [f"题库第 {items[0]['id']} 题（{_state_label(items[0]['state'])}）："]
        else:
            lines = [
                f"共 {result['total']} 道题符合条件（state={result['state']}），"
                f"下面是最新的 {len(items)} 道："
            ]
        lines.extend(_question_line(item) for item in items)
        lines.append(
            "要重练时让用户在题库界面开始；不要把题目当成聊天文本直接发给用户。"
        )
        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={
                "total": result["total"],
                "state": result["state"],
                "items": [
                    {
                        "id": item["id"],
                        "type": item["type"],
                        "state": item["state"],
                        "bookmarked": item["bookmarked"],
                        "concepts": item["concepts"],
                        "question": item["question"],
                        **({"answer": item["answer"]} if item.get("answer") else {}),
                    }
                    for item in items
                ],
            },
        )
    except Exception as exc:
        logger.error("bank_list failed: %s", exc)
        return ToolResult(ok=False, content=f"题库读取失败: {exc}")


def bank_bookmark(
    question_id: int,
    bookmarked: bool = True,
    workspace: str = ".",
) -> ToolResult:
    """Mark or unmark one bank question for the learner."""
    try:
        from service.quiz_service import QuizService

        result = QuizService(workspace).bookmark_question(
            int(question_id), bool(bookmarked)
        )
        if not result.get("ok"):
            return ToolResult(ok=False, content=result.get("error", "标记失败。"))
        action = "已加入收藏" if result["bookmarked"] else "已取消收藏"
        return ToolResult(
            ok=True,
            content=f"题目 #{result['question_id']} {action}。",
            data={
                "question_id": result["question_id"],
                "bookmarked": result["bookmarked"],
            },
        )
    except Exception as exc:
        logger.error("bank_bookmark failed: %s", exc)
        return ToolResult(ok=False, content=f"标记失败: {exc}")


register_tool(
    name="bank_overview",
    description=(
        "Summarize the saved practice question bank: how many questions exist, "
        "how they are distributed across answered states, and the top concepts."
    ),
    params_schema={"type": "object", "properties": {}, "required": []},
    func=bank_overview,
)

register_tool(
    name="bank_list",
    description=(
        "List saved practice questions from the question bank, optionally filtered "
        "by state (all/unanswered/correct/partial/incorrect/bookmarked), concept, "
        "material, course, difficulty or question type. Pass question_id to read the "
        "single question the user is referring to (e.g. from a 「问 AI」 hand-off). "
        "Read-only: it never starts a practice."
    ),
    params_schema={
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "enum": ["all", "unanswered", "correct", "partial", "incorrect", "bookmarked"],
                "description": "Which bank state to list (default all)",
            },
            "question_id": {
                "type": "integer",
                "description": "Read exactly this question (for a 「问 AI」 reference)",
            },
            "concept": {"type": "string", "description": "Optional concept name filter"},
            "course": {"type": "string", "description": "Optional course/source substring filter"},
            "difficulty": {
                "type": "string",
                "enum": ["easy", "medium", "hard"],
                "description": "Optional difficulty filter",
            },
            "source": {
                "type": "string",
                "description": "Optional exact material filter (from bank_overview by_source)",
            },
            "question_type": {
                "type": "string",
                "description": "Optional question type filter: single_choice, true_false, short_answer",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of questions to return (default 20, max 100)",
            },
        },
        "required": [],
    },
    func=bank_list,
)

register_tool(
    name="bank_bookmark",
    description=(
        "Bookmark or unbookmark one saved question in the question bank. Use only "
        "when the learner asks to keep or drop a question."
    ),
    params_schema={
        "type": "object",
        "properties": {
            "question_id": {
                "type": "integer",
                "description": "Question id from bank_list or bank_overview",
            },
            "bookmarked": {
                "type": "boolean",
                "description": "True to bookmark, false to remove the bookmark",
            },
        },
        "required": ["question_id"],
    },
    func=bank_bookmark,
)
