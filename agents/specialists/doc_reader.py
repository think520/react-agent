"""DocReaderSpecialist — read long documents/notes, return digest.

Value: context isolation. The parent LLM doesn't get a wall of text;
it gets a structured digest. The specialist session is isolated so the
long read doesn't pollute parent history.
"""
from __future__ import annotations

from typing import Any

from agents.base import BaseSpecialist


class DocReaderSpecialist(BaseSpecialist):
    @property
    def name(self) -> str:
        return "doc_reader"

    @property
    def description(self) -> str:
        return "Read long documents or notes and return a concise digest. Isolates the heavy read in a fresh session."

    @property
    def system_prompt_template(self) -> str:
        return (
            "You are bobodan's {specialist_name} specialist. "
            "You read long documents and return concise digests.\n\n"
            "Rules:\n"
            "- Output a short summary (3-5 bullet points, ≤ 200 words).\n"
            "- Use each source path exactly as provided in source_paths.\n"
            "- Do NOT shorten paths to basenames.\n"
            "- When source_paths are present, call read_file with those exact path strings before summarizing.\n"
            "- Use read_file, rag_search, knowledge_status as needed.\n"
            "- Do NOT call delegate_* tools (you have none in v1).\n"
            "- Do NOT call memory_* tools (you have none in v1).\n"
            "- Allowed tools: {allowed_tools}\n\n"
            "Task: {task}\n"
        )

    @property
    def default_max_iterations(self) -> int:
        return 5

    @property
    def default_timeout_seconds(self) -> int:
        return 60

    @property
    def default_allowed_tools(self) -> list[str]:
        return ["read_file", "rag_search", "knowledge_status"]

    @property
    def default_provider(self) -> str:
        return "minimax"

    @property
    def default_model(self) -> str:
        return "MiniMax-M2.7"

    def data_to_content(self, result: Any, content_cap: int) -> str:
        if not isinstance(result, dict):
            return str(result)
        points = result.get("key_points") or result.get("points") or []
        sources = result.get("source_files") or result.get("sources") or []
        char_count = result.get("char_count")
        lines = []
        if points:
            lines.append("Key points:")
            for p in points:
                lines.append(f"- {p}")
        if sources:
            lines.append(f"\nSources: {', '.join(str(s) for s in sources)}")
        if char_count is not None:
            lines.append(f"\n[read {char_count} chars]")
        return "\n".join(lines) if lines else str(result)
