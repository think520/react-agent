"""Register 3 delegate tools (delegate_doc_reader / delegate_triage /
delegate_planner) that hand off work to specialists via the runner.

Called from REPL.initialize() after the SpecialistRegistry is built.
"""
from __future__ import annotations

import logging
from typing import Any

from agents.registry import SpecialistRegistry
from agents.runner import run_specialist
from core.session import Session
from tools.base import ToolResult, register_tool

logger = logging.getLogger(__name__)


def register_delegate_tools(
    registry: SpecialistRegistry,
    get_session: "Any",  # callable returning the current parent Session
    get_app_config: "Any",  # callable returning the current app config dict
) -> int:
    """Register the 3 delegate tools. Returns count registered.

    Args:
        registry: SpecialistRegistry with all 3 specialists loaded.
        get_session: callable returning the current parent Session (REPL holds it).
        get_app_config: callable returning the current app config dict.
    """
    count = 0
    for name in registry.list_names():
        schema = _schema_for(name)
        func = _make_delegate_func(name, registry, get_session, get_app_config)
        register_tool(
            name=f"delegate_{name}",
            description=_description_for(name),
            params_schema=schema,
            func=func,
        )
        count += 1
    logger.info("Registered %d delegate tools", count)
    return count


def _make_delegate_func(
    name: str,
    registry: SpecialistRegistry,
    get_session: "Any",
    get_app_config: "Any",
):
    """Build the callable that REPL's execute_tool() will invoke."""
    def delegate(**kwargs) -> ToolResult:
        # The 'task' field is the curated context; specialist may accept
        # additional structured fields per its schema.
        task = kwargs.get("task") or kwargs.get("query") or kwargs.get("goal") or str(kwargs)
        parent_session: Session = get_session()
        app_config = get_app_config()
        return run_specialist(registry, name, str(task), parent_session, app_config)
    delegate.__name__ = f"delegate_{name}"
    delegate.__qualname__ = f"delegate_{name}"
    return delegate


def _description_for(name: str) -> str:
    return {
        "doc_reader": (
            "Read long documents or notes and return a concise digest. "
            "Use when the user pastes a long file or asks for a summary of a specific source."
        ),
        "triage": (
            "Classify the user's query into a task_type and recommend a specialist. "
            "Use when the user query is ambiguous or you need help deciding which specialist to use."
        ),
        "planner": (
            "Generate a learning plan for a user goal. "
            "Use when the user wants a structured study plan, with optional course and deadline."
        ),
    }.get(name, f"Delegate to {name} specialist.")


def _schema_for(name: str) -> dict:
    return {
        "doc_reader": {
            "type": "object",
            "properties": {
                "user_goal": {
                    "type": "string",
                    "description": "What the user wants to learn from the document.",
                },
                "source_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file or directory paths to read.",
                },
                "desired_output": {
                    "type": "string",
                    "description": "What shape the result should be in (e.g. '3-5 bullets').",
                },
                "constraints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional constraints (e.g. 'no more than 200 words').",
                },
                "task": {
                    "type": "string",
                    "description": "Freeform fallback if structured fields are empty.",
                },
            },
            "required": ["user_goal", "source_paths"],
        },
        "triage": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user's original question or task description.",
                },
                "context_hints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional hints about topic, course, or user intent.",
                },
                "task": {
                    "type": "string",
                    "description": "Freeform fallback.",
                },
            },
            "required": ["query"],
        },
        "planner": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "What the user wants to learn.",
                },
                "course": {
                    "type": "string",
                    "description": "Optional related course name.",
                },
                "deadline": {
                    "type": "string",
                    "description": "Optional deadline as YYYY-MM-DD.",
                },
                "desired_plan_length_days": {
                    "type": "integer",
                    "description": "Optional target plan length in days (default 14).",
                },
                "task": {
                    "type": "string",
                    "description": "Freeform fallback.",
                },
            },
            "required": ["goal"],
        },
    }.get(name, {"type": "object", "properties": {}})
