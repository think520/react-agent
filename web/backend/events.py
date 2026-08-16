"""Convert internal AgentLoop events into stable Web events.

Internal events are canonicalized through core.agent_events (AG-0.2) and then
translated here into the stable SSE event names the frontend already consumes.
The outward event names must never change.
"""

from __future__ import annotations

from typing import Any

from core.agent_events import (
    MESSAGE_DELTA,
    MESSAGE_END,
    SPECIALIST_EVENT,
    TOOL_END,
    TOOL_START,
    canonical_type,
)

_TOOL_STATUS = {
    "rag_search": "正在查找你的资料",
    "question_generate": "正在生成练习题",
    "quiz_start": "正在准备练习",
    "quiz_submit": "正在批改答案",
    "learning_path": "正在整理学习路线",
    "learning_review": "正在整理复习内容",
    "learning_progress": "正在更新学习进度",
    "obsidian_sync": "正在同步资料",
    "request_web_search": "正在确认是否需要联网补充",
    "web_research": "正在搜索并读取网页资料",
    "request_memory_confirmation": "正在整理需要你确认的记忆",
}

_TOOL_COMPLETED_STATUS = {
    "rag_search": "已找到相关本地资料",
    "question_generate": "练习题已经准备好",
    "quiz_start": "练习已经准备好",
    "web_research": "网页证据已经准备好",
    "request_web_search": "等待你确认是否联网",
    "request_memory_confirmation": "等待你确认是否记住",
}


_TOOL_STATUS.update({
    "concept_map_query": "正在查询知识地图",
    "concept_map_status": "正在读取知识地图状态",
})
_TOOL_COMPLETED_STATUS.update({
    "concept_map_query": "知识地图关系已准备好",
    "concept_map_status": "知识地图状态已读取",
})


def to_web_events(event: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    # Canonicalize first so the adapter speaks the AG-0.2 naming contract.
    event_type = canonical_type(event.get("type"))

    if event_type == MESSAGE_DELTA:
        return [("message_delta", {"content": event.get("content", "")})]

    if event_type == TOOL_START:
        tool_name = str(event.get("tool_name", ""))
        return [("status", {
            "phase": "running",
            "message": _TOOL_STATUS.get(tool_name, "正在处理"),
            "tool_name": tool_name,
        })]

    if event_type == TOOL_END:
        web_events: list[tuple[str, dict[str, Any]]] = [("status", {
            "phase": "completed" if event.get("ok") else "failed",
            "message": _TOOL_COMPLETED_STATUS.get(str(event.get("tool_name") or ""), "处理完成") if event.get("ok") else "处理失败",
            "tool_name": event.get("tool_name"),
            "elapsed": event.get("elapsed"),
        })]
        for artifact in event.get("artifacts") or []:
            artifact_type = artifact.get("type")
            if artifact_type in {"citation", "practice", "learning_update"}:
                web_events.append((artifact_type, artifact))
            elif artifact_type == "knowledge_context":
                web_events.append(("chat_artifact", {"artifact": artifact}))
            elif artifact_type in {"web_consent", "web_candidates", "web_evidence", "practice_ready", "memory_confirmation"}:
                web_events.append(("chat_artifact", {"artifact": artifact}))
        return web_events

    if event_type == MESSAGE_END:
        return []

    if event_type == SPECIALIST_EVENT:
        return []

    return []
