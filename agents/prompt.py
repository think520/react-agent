"""System prompt rendering for specialists.

v1 uses a simple template: one prompt per specialist, rendered with
the task and basic context. Future v2 can add per-task context injection,
memory snippets, or per-user customization.
"""
from __future__ import annotations


def render_specialist_prompt(
    template: str,
    task: str,
    specialist_name: str,
    allowed_tools: list[str],
) -> str:
    """Render a specialist's system prompt template.

    The template receives:
      {specialist_name} — the specialist's registered name
      {task} — the task description (curated by the parent LLM)
      {allowed_tools} — comma-joined tool list (for awareness)
    """
    return template.format(
        specialist_name=specialist_name,
        task=task,
        allowed_tools=", ".join(allowed_tools),
    )
