"""Chat run endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.session import Session
from service.agent_service import AgentService
from web.backend.deps import (
    get_config,
    get_default_provider_name,
    get_session_save_dir,
    get_workspace,
)
from web.backend.sse import encode_sse

router = APIRouter()


class ChatRunRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    provider: str | None = None
    save: bool = True


def _load_or_create_session(session_id: str | None, config: dict[str, Any]) -> Session:
    save_dir = get_session_save_dir(config)
    if session_id:
        result = AgentService.load_session(session_id, save_dir)
        if not result["ok"]:
            raise HTTPException(status_code=404, detail=result["error"])
        return result["session"]

    max_messages = config.get("session", {}).get("max_messages")
    return Session.new(get_workspace(), max_messages=max_messages)


@router.post("/runs")
def create_run(request: ChatRunRequest) -> StreamingResponse:
    """Run one agent turn and stream events as SSE."""
    config = get_config()
    provider_name = request.provider or get_default_provider_name(config)
    provider_result = AgentService.create_provider(config, provider_name)
    if not provider_result["ok"]:
        raise HTTPException(status_code=400, detail=provider_result["error"])

    session = _load_or_create_session(request.session_id, config)

    def event_stream():
        yield encode_sse("run_start", {
            "session_id": session.session_id,
            "provider": provider_name,
        })
        try:
            events = AgentService.run_stream(
                session=session,
                user_input=request.message,
                provider=provider_result["provider"],
            )
            for event in events:
                yield encode_sse(event.get("type", "message"), event)
            if request.save:
                save_result = AgentService.save_session(
                    session,
                    get_session_save_dir(config),
                )
                if not save_result["ok"]:
                    yield encode_sse("error", save_result)
            yield encode_sse("run_end", {"session_id": session.session_id})
        except Exception as exc:
            yield encode_sse("error", {"ok": False, "error": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
