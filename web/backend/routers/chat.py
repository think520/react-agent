"""Chat run and session endpoints."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.session import Session
from service.agent_service import AgentService
from tools import get_tools_schema
from web.backend.deps import (
    get_config,
    get_default_provider_name,
    get_runtime_context,
    get_session_save_dir,
)
from web.backend.errors import APIError
from web.backend.events import to_web_events
from web.backend.schemas import ChatRunRequest, ChatSessionUpdateRequest
from web.backend.sse import encode_sse

router = APIRouter()
logger = logging.getLogger(__name__)

_WEB_TOOL_NAMES = frozenset({
    "rag_search",
    "graph_query",
    "knowledge_status",
    "question_generate",
    "quiz_start",
    "quiz_submit",
    "learning_path",
    "learning_progress",
    "learning_review",
    "memory_save",
    "memory_recall",
    "memory_daily_save",
    "memory_daily_read",
    "memory_promote",
})


def _web_tools_schema() -> list[dict]:
    return [
        schema for schema in get_tools_schema()
        if schema.get("function", {}).get("name") in _WEB_TOOL_NAMES
    ]


def _load_or_create_session(chat_session_id: str | None, config: dict[str, Any]) -> Session:
    save_dir = get_session_save_dir(config)
    if chat_session_id:
        result = AgentService.load_session(chat_session_id, save_dir)
        if not result["ok"]:
            raise APIError(404, "session_not_found", result["error"])
        return result["session"]

    runtime = get_runtime_context()
    max_messages = config.get("session", {}).get("max_messages")
    return Session.new(runtime.workspace, max_messages=max_messages)


def _session_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "chat_session_id": summary.get("session_id", ""),
        "name": summary.get("name", ""),
        "created_at": summary.get("created_at", ""),
        "last_active": summary.get("last_active", ""),
        "message_count": summary.get("message_count", 0),
    }


def _session_detail(session: Session) -> dict[str, Any]:
    messages = []
    for message in session.messages:
        role = message.get("role")
        content = message.get("content") or ""
        if role == "user":
            messages.append({"role": "user", "content": content})
        elif role == "assistant" and not message.get("tool_calls") and content:
            messages.append({"role": "assistant", "content": content})
    return {
        "chat_session_id": session.session_id,
        "name": session.name,
        "created_at": session.created_at,
        "last_active": session.last_active,
        "message_count": len(messages),
        "messages": messages,
    }


@router.get("/sessions")
def list_sessions() -> dict:
    result = AgentService.list_sessions(get_session_save_dir(get_config()))
    return {"sessions": [_session_summary(item) for item in result["sessions"]]}


@router.get("/sessions/{chat_session_id}")
def get_session(chat_session_id: str) -> dict:
    result = AgentService.load_session(chat_session_id, get_session_save_dir(get_config()))
    if not result["ok"]:
        raise APIError(404, "session_not_found", result["error"])
    return _session_detail(result["session"])


@router.patch("/sessions/{chat_session_id}")
def rename_session(chat_session_id: str, request: ChatSessionUpdateRequest) -> dict:
    result = AgentService.rename_session(
        chat_session_id,
        get_session_save_dir(get_config()),
        request.name,
    )
    if not result["ok"]:
        raise APIError(404, "session_not_found", result["error"])
    return {"chat_session_id": result["session_id"], "name": request.name.strip()}


@router.delete("/sessions/{chat_session_id}")
def delete_session(chat_session_id: str) -> dict:
    result = AgentService.delete_session(chat_session_id, get_session_save_dir(get_config()))
    if not result["ok"]:
        raise APIError(404, "session_not_found", result["error"])
    return {"deleted": True, "chat_session_id": result["session_id"]}


@router.post("/runs")
def create_run(request: ChatRunRequest) -> StreamingResponse:
    config = get_config()
    runtime = get_runtime_context()
    provider_name = request.provider or get_default_provider_name(config)
    try:
        provider = runtime.create_provider(provider_name)
    except Exception as exc:
        logger.warning("Web provider creation failed for %s: %s", provider_name, exc)
        raise APIError(
            503,
            "provider_unavailable",
            "The selected AI provider is unavailable. Check its configuration and try again.",
        ) from exc

    session = _load_or_create_session(request.chat_session_id, config)
    run_id = str(uuid.uuid4())

    def event_stream():
        yield encode_sse("run_started", {
            "run_id": run_id,
            "chat_session_id": session.session_id,
            "provider": provider_name,
        })
        try:
            runtime.refresh_memory()
            events = AgentService.run_stream(
                session=session,
                user_input=request.message,
                provider=provider,
                skills_prompt=runtime.skills_prompt,
                memory_prompt=runtime.memory_prompt,
                trace_writer=runtime.create_trace(session.session_id),
                tools_schema=_web_tools_schema(),
                allowed_tool_names=_WEB_TOOL_NAMES,
            )
            termination_reason = "final_answer"
            for event in events:
                if event.get("type") == "assistant_done":
                    termination_reason = event.get("termination_reason", "final_answer")
                for web_event, payload in to_web_events(event):
                    yield encode_sse(web_event, {"run_id": run_id, **payload})

            if request.save:
                save_result = AgentService.save_session(session, get_session_save_dir(config))
                if not save_result["ok"]:
                    yield encode_sse("run_failed", {
                        "run_id": run_id,
                        "error": {
                            "code": "session_save_failed",
                            "message": "The conversation could not be saved.",
                        },
                    })
                    return

            yield encode_sse("run_completed", {
                "run_id": run_id,
                "chat_session_id": session.session_id,
                "termination_reason": termination_reason,
            })
        except Exception as exc:
            logger.exception("Web chat run failed: %s", exc)
            yield encode_sse("run_failed", {
                "run_id": run_id,
                "error": {
                    "code": "run_failed",
                    "message": "The AI run failed. Please try again.",
                },
            })

    return StreamingResponse(event_stream(), media_type="text/event-stream")
