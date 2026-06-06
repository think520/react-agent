"""TriageSpecialist — classify a user query and recommend routing.

Value: model substitution + sandbox. Uses a fast/cheap model
(deepseek-v4-flash by default) and a tight tool set. Returns a
structured decision (task_type, recommended_specialist, confidence,
reason, should_delegate) so the parent LLM knows what to do next.
"""
from __future__ import annotations

import json
from typing import Any

from agents.base import BaseSpecialist


class TriageSpecialist(BaseSpecialist):
    @property
    def name(self) -> str:
        return "triage"

    @property
    def description(self) -> str:
        return "Classify a query into a task_type and recommend a specialist. Fast/cheap model, no delegation."

    @property
    def system_prompt_template(self) -> str:
        return (
            "You are bobodan's {specialist_name} specialist. "
            "You classify the user's query and return a routing decision.\n\n"
            "Output ONLY a JSON object with these exact fields:\n"
            "{{\n"
            '  "task_type": "<one of: document_summary, plan_request, general_qa, other>",\n'
            '  "recommended_specialist": "<one of: doc_reader, planner, (none) — must match a registered specialist>",\n'
            '  "confidence": <0.0 to 1.0>,\n'
            '  "reason": "<one short sentence>",\n'
            '  "should_delegate": <true|false>\n'
            "}}\n\n"
            "Rules:\n"
            "- If unsure, set should_delegate=false and recommended_specialist=(none).\n"
            "- Do NOT call delegate_* tools.\n"
            "- Do NOT call memory_* tools.\n"
            "- Allowed tools: {allowed_tools}\n\n"
            "Task: {task}\n"
        )

    @property
    def default_max_iterations(self) -> int:
        return 2

    @property
    def default_timeout_seconds(self) -> int:
        return 30

    @property
    def default_allowed_tools(self) -> list[str]:
        return ["read_file", "knowledge_status"]

    @property
    def default_provider(self) -> str:
        return "deepseek"

    @property
    def default_model(self) -> str:
        return "deepseek-v4-flash"

    def data_to_content(self, result: Any, content_cap: int) -> str:
        if not isinstance(result, dict):
            # Best effort: try to parse the result string as JSON
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except (json.JSONDecodeError, ValueError):
                    return result
            else:
                return str(result)
        task_type = result.get("task_type", "?")
        rec = result.get("recommended_specialist", "(none)")
        conf = result.get("confidence", 0)
        reason = result.get("reason", "")
        should = result.get("should_delegate", False)
        try:
            conf_text = f"{float(conf):.2f}"
        except (TypeError, ValueError):
            conf_text = str(conf)
        lines = [
            "**Triage decision**",
            f"- task_type: `{task_type}`",
            f"- recommended_specialist: `{rec}` (confidence {conf_text})",
            f"- should_delegate: `{should}`",
            f"- reason: {reason}",
        ]
        return "\n".join(lines)
