"""PlannerSpecialist — generate a learning plan via the learning_tools.

Value: state-write orchestration. Uses learning_path / learning_progress
to generate and persist a plan, returning a user-facing preview plus
the full plan dict in data.result.
"""
from __future__ import annotations

from typing import Any

from agents.base import BaseSpecialist


class PlannerSpecialist(BaseSpecialist):
    @property
    def name(self) -> str:
        return "planner"

    @property
    def description(self) -> str:
        return "Generate a learning plan for a goal. Uses learning_path / learning_progress; persists to learning store."

    @property
    def system_prompt_template(self) -> str:
        return (
            "You are bobodan's {specialist_name} specialist. "
            "You generate learning plans for the user.\n\n"
            "Rules:\n"
            "- Use learning_path to generate the plan; learning_progress to check current mastery.\n"
            "- Output a structured plan with title, steps, optional course/deadline.\n"
            "- Do NOT call delegate_* tools.\n"
            "- Do NOT call memory_* tools.\n"
            "- Allowed tools: {allowed_tools}\n\n"
            "Task: {task}\n"
        )

    @property
    def default_max_iterations(self) -> int:
        return 8

    @property
    def default_timeout_seconds(self) -> int:
        return 120

    @property
    def default_allowed_tools(self) -> list[str]:
        return ["learning_path", "learning_progress"]

    @property
    def default_provider(self) -> str:
        return "minimax"

    @property
    def default_model(self) -> str:
        return "MiniMax-M2.7"

    def data_to_content(self, result: Any, content_cap: int) -> str:
        if not isinstance(result, dict):
            return str(result)
        title = result.get("title", "Untitled plan")
        steps = result.get("steps", [])
        deadline = result.get("deadline")
        lines = [f"**{title}**", ""]
        for i, step in enumerate(steps[:7], 1):
            if isinstance(step, dict):
                day = step.get("day", i)
                topic = step.get("topic", step.get("title", str(step)))
                lines.append(f"{i}. (Day {day}) {topic}")
            else:
                lines.append(f"{i}. {step}")
        if len(steps) > 7:
            lines.append(f"... ({len(steps) - 7} more steps)")
        if deadline:
            lines.append(f"\nDeadline: {deadline}")
        return "\n".join(lines)
