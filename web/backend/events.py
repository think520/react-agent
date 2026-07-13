"""Convert internal AgentLoop events into stable Web events."""

from __future__ import annotations

from typing import Any


_TOOL_STATUS = {
    "rag_search": "正在查找你的资料",
    "question_generate": "正在生成练习题",
    "quiz_start": "正在准备练习",
    "quiz_submit": "正在批改答案",
    "learning_path": "正在整理学习路线",
    "learning_review": "正在整理复习内容",
    "learning_progress": "正在更新学习进度",
    "obsidian_sync": "正在同步资料",
}


def to_web_events(event: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    event_type = event.get("type")

    if event_type == "assistant_delta":
        return [("message_delta", {"content": event.get("content", "")})]

    if event_type == "tool_start":
        tool_name = str(event.get("tool_name", ""))
        return [("status", {
            "phase": "running",
            "message": _TOOL_STATUS.get(tool_name, "正在处理"),
            "tool_name": tool_name,
        })]

    if event_type == "tool_end":
        web_events: list[tuple[str, dict[str, Any]]] = [("status", {
            "phase": "completed" if event.get("ok") else "failed",
            "message": "处理完成" if event.get("ok") else "处理失败",
            "tool_name": event.get("tool_name"),
            "elapsed": event.get("elapsed"),
        })]
        for artifact in event.get("artifacts") or []:
            artifact_type = artifact.get("type")
            if artifact_type in {"citation", "practice", "learning_update"}:
                web_events.append((artifact_type, artifact))
        return web_events

    if event_type == "assistant_done":
        return []

    if event_type == "specialist_event":
        return []

    return []
