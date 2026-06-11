"""Obsidian export tools — learning plans and quiz summaries to Markdown."""

import json
import os
from datetime import datetime, timezone

from .base import ToolResult, _is_within_workspace, _resolve_path, register_tool


def _format_concept_link(concept: str) -> str:
    """Wrap a concept name in Obsidian wikilink format."""
    return f"[[{concept}]]"


def obsidian_export_plan(
    plan_id: int,
    vault_path: str,
    cwd: str = ".",
    workspace: str = ".",
) -> ToolResult:
    """Export a learning plan to Obsidian Markdown with frontmatter, checkboxes, and wikilinks."""
    from learning.store import LearningStore

    resolved_vault = _resolve_path(vault_path, cwd)
    if not _is_within_workspace(resolved_vault, workspace):
        return ToolResult(ok=False, content=f"Access denied: {vault_path} is outside workspace")

    store = LearningStore(workspace)
    plan = store.get_plan(plan_id)
    if not plan:
        return ToolResult(ok=False, content=f"Learning plan not found: id={plan_id}")

    # Collect all concepts from steps
    all_concepts: list[str] = []

    steps_lines: list[str] = []
    for step in plan.steps:
        day = step.get("day", "?")
        date = step.get("date", "")
        topics = step.get("topics", [])
        tasks = step.get("tasks", [])
        materials = step.get("materials", [])
        review = step.get("review", [])

        all_concepts.extend(topics)
        all_concepts.extend(review)

        date_suffix = f" ({date})" if date else ""
        steps_lines.append(f"### Day {day}{date_suffix}")

        if topics:
            topic_links = ", ".join(_format_concept_link(t) for t in topics)
            steps_lines.append(f"**知识点**: {topic_links}")

        if materials:
            steps_lines.append("**资料**:")
            for m in materials:
                steps_lines.append(f"  - {m}")

        if tasks:
            for t in tasks:
                steps_lines.append(f"- [ ] {t}")

        if review:
            review_links = ", ".join(_format_concept_link(r) for r in review)
            steps_lines.append(f"**复习**: {review_links}")

        steps_lines.append("")

    # Deduplicate concepts
    unique_concepts = list(dict.fromkeys(all_concepts))

    # Build markdown
    lines = [
        "---",
        f"title: \"{plan.title}\"",
        f"goal: \"{plan.goal}\"",
        f"course: \"{plan.course or ''}\"",
        f"deadline: \"{plan.deadline or ''}\"",
        f"created: \"{plan.created_at}\"",
        "type: learning-plan",
        "---",
        "",
        f"# {plan.title}",
        "",
        f"**目标**: {plan.goal}",
    ]
    if plan.course:
        lines.append(f"**课程**: {plan.course}")
    if plan.deadline:
        lines.append(f"**截止日期**: {plan.deadline}")
    lines.append("")
    lines.append("## 学习步骤")
    lines.append("")
    lines.extend(steps_lines)

    if unique_concepts:
        lines.append("## 相关知识点")
        lines.append("")
        for c in unique_concepts:
            lines.append(f"- {_format_concept_link(c)}")
        lines.append("")

    content = "\n".join(lines)

    # Write file
    export_dir = os.path.join(resolved_vault, "学习计划")
    os.makedirs(export_dir, exist_ok=True)
    # Sanitize filename
    safe_title = plan.title.replace("/", "_").replace("\\", "_").replace(":", "_")
    file_path = os.path.join(export_dir, f"{safe_title}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return ToolResult(
        ok=True,
        content=f"学习计划已导出: {file_path}",
        data={"file_path": file_path, "concepts": unique_concepts},
    )


def obsidian_export_quiz_summary(
    vault_path: str,
    course: str | None = None,
    cwd: str = ".",
    workspace: str = ".",
) -> ToolResult:
    """Export quiz summary (wrong answers, weakness analysis, mastery) to Obsidian Markdown."""
    from quiz.store import QuizStore
    from learning.store import LearningStore

    resolved_vault = _resolve_path(vault_path, cwd)
    if not _is_within_workspace(resolved_vault, workspace):
        return ToolResult(ok=False, content=f"Access denied: {vault_path} is outside workspace")

    quiz_store = QuizStore(workspace)
    learning_store = LearningStore(workspace)

    # Gather data
    wrong_answers = quiz_store.get_wrong_answers(limit=50)
    weakness = quiz_store.get_weakness_analysis()
    all_mastery = learning_store.list_mastery(limit=200)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "---",
        "title: 做题总结",
        f"date: \"{today}\"",
        f"course: \"{course or ''}\"",
        "type: quiz-summary",
        "---",
        "",
        f"# 做题总结 — {today}",
        "",
    ]

    # Wrong answer book grouped by concept
    if wrong_answers:
        # Group by concept
        by_concept: dict[str, list[dict]] = {}
        for entry in wrong_answers:
            concepts = entry.get("concepts", [])
            if isinstance(concepts, str):
                try:
                    concepts = json.loads(concepts)
                except (json.JSONDecodeError, TypeError):
                    concepts = [concepts] if concepts else ["未分类"]
            if not concepts:
                concepts = ["未分类"]
            for concept in concepts:
                by_concept.setdefault(concept, []).append(entry)

        lines.append("## 错题本")
        lines.append("")
        for concept, entries in by_concept.items():
            lines.append(f"### {_format_concept_link(concept)}")
            lines.append("")
            for i, e in enumerate(entries, 1):
                q_text = e.get("question", "")
                user_ans = e.get("user_answer", "")
                correct_ans = e.get("answer", "")
                explanation = e.get("explanation", "")
                q_type = e.get("type", "")
                difficulty = e.get("difficulty", "")

                label_parts = []
                if q_type:
                    from quiz.review import _type_label
                    label_parts.append(_type_label(q_type))
                if difficulty:
                    label_parts.append(difficulty)
                label = f" ({', '.join(label_parts)})" if label_parts else ""

                lines.append(f"{i}. **{q_text}**{label}")
                lines.append(f"   - 你的答案: {user_ans} (x)")
                lines.append(f"   - 正确答案: {correct_ans}")
                if explanation:
                    lines.append(f"   - 解析: {explanation}")
                lines.append("")
    else:
        lines.append("## 错题本")
        lines.append("")
        lines.append("暂无错题记录。")
        lines.append("")

    # Weakness analysis table
    lines.append("## 薄弱点分析")
    lines.append("")
    if weakness:
        lines.append("| 知识点 | 做题数 | 错误数 | 错误率 |")
        lines.append("|--------|--------|--------|--------|")
        for w in weakness:
            concept = w.get("concept", "")
            total = w.get("total_attempts", 0)
            wrong = w.get("wrong_count", 0)
            rate = w.get("error_rate", 0.0)
            lines.append(f"| {_format_concept_link(concept)} | {total} | {wrong} | {rate:.0%} |")
        lines.append("")
    else:
        lines.append("暂无做题记录，无法分析薄弱点。")
        lines.append("")

    # Mastery overview
    lines.append("## 掌握度概览")
    lines.append("")
    if all_mastery:
        lines.append("| 知识点 | 状态 | 分数 |")
        lines.append("|--------|------|------|")
        for m in all_mastery:
            status_cn = {
                "unseen": "未接触",
                "learning": "学习中",
                "mastered": "已掌握",
                "needs_review": "需复习",
            }.get(m.status, m.status)
            lines.append(f"| {_format_concept_link(m.concept)} | {status_cn} | {m.score:.2f} |")
        lines.append("")
    else:
        lines.append("暂无掌握度数据。")
        lines.append("")

    content = "\n".join(lines)

    # Write file
    export_dir = os.path.join(resolved_vault, "做题总结")
    os.makedirs(export_dir, exist_ok=True)
    file_path = os.path.join(export_dir, f"{today}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return ToolResult(
        ok=True,
        content=f"做题总结已导出: {file_path}",
        data={"file_path": file_path, "wrong_count": len(wrong_answers), "weakness_count": len(weakness)},
    )


register_tool(
    "obsidian_export_plan",
    "Export a learning plan to Obsidian Markdown with frontmatter, checkbox tasks, and [[wikilink]] concepts.",
    {
        "type": "object",
        "properties": {
            "plan_id": {"type": "integer", "description": "ID of the learning plan to export"},
            "vault_path": {"type": "string", "description": "Obsidian vault path, relative to cwd or absolute within workspace"},
        },
        "required": ["plan_id", "vault_path"],
    },
    obsidian_export_plan,
)

register_tool(
    "obsidian_export_quiz_summary",
    "Export quiz summary to Obsidian Markdown: wrong answer book grouped by concept, weakness analysis table, and mastery overview.",
    {
        "type": "object",
        "properties": {
            "vault_path": {"type": "string", "description": "Obsidian vault path, relative to cwd or absolute within workspace"},
            "course": {"type": "string", "description": "Optional course name to filter quiz data"},
        },
        "required": ["vault_path"],
    },
    obsidian_export_quiz_summary,
)
