"""User-confirmed web search and evidence endpoints."""

from __future__ import annotations

from datetime import datetime
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.session import Session
from research.providers import SearchProviderError
from service.agent_service import AgentService
from service.preference_service import PreferenceService
from service.research_service import ResearchService
from web.backend.capabilities import WEB_SKILL_NAMES
from web.backend.deps import (
    get_config,
    get_default_provider_name,
    get_request_library_id,
    get_request_workspace,
    get_session_save_dir,
)
from web.backend.errors import APIError


router = APIRouter()


class WebSearchRequest(BaseModel):
    chat_session_id: str | None = None
    query: str = Field(..., min_length=1, max_length=500)
    consent_artifact_id: str | None = Field(default=None, max_length=64)
    append_user_message: bool = False


class WebConsentRejectRequest(BaseModel):
    chat_session_id: str


class WebSourceSelectRequest(BaseModel):
    chat_session_id: str
    candidate_ids: list[str] = Field(..., min_length=1, max_length=4)


def _preferences() -> dict:
    config = get_config()
    return PreferenceService(get_default_provider_name(config), sorted(WEB_SKILL_NAMES)).get()


def _load_session(request: Request, session_id: str | None) -> Session:
    config = get_config()
    workspace = get_request_workspace(request)
    library_id = get_request_library_id(request)
    if session_id:
        result = AgentService.load_session(session_id, get_session_save_dir(config, workspace))
        if not result.get("ok"):
            raise APIError(404, "session_not_found", "Conversation not found in this library.")
        session = result["session"]
        if session.library_id and session.library_id != library_id:
            raise APIError(404, "session_not_found", "Conversation not found in this library.")
    else:
        session = Session.new(workspace, max_messages=config.get("session", {}).get("max_messages"))
    session.library_id = library_id
    return session


def _save_session(request: Request, session: Session) -> None:
    result = AgentService.save_session(session, get_session_save_dir(get_config(), get_request_workspace(request)))
    if not result.get("ok"):
        raise APIError(500, "session_save_failed", "The web research state could not be saved.")


def _find_artifact(session: Session, artifact_id: str, artifact_type: str | None = None) -> dict | None:
    for message in session.messages:
        for artifact in message.get("artifacts") or []:
            if artifact.get("artifact_id") == artifact_id and (not artifact_type or artifact.get("type") == artifact_type):
                return artifact
    return None


def _append_artifact(session: Session, content: str, artifact: dict) -> None:
    session.messages.append({"role": "assistant", "content": content, "artifacts": [artifact]})
    session.last_active = datetime.now().isoformat()
    session._trim_messages()


@router.post("/searches")
def create_search(body: WebSearchRequest, request: Request) -> dict:
    session = _load_session(request, body.chat_session_id)
    if body.append_user_message:
        session.add_message("user", body.query.strip())
        if not session.name:
            session.name = body.query.strip()[:30]
            session.name_source = "fallback"
    if body.consent_artifact_id:
        consent = _find_artifact(session, body.consent_artifact_id, "web_consent")
        if not consent:
            raise APIError(404, "web_consent_not_found", "The web search confirmation is no longer available.")
        if consent.get("status") != "pending":
            raise APIError(409, "web_consent_resolved", "The web search confirmation has already been handled.")
        consent["status"] = "approved"

    provider = _preferences().get("search", {}).get("provider", "auto")
    try:
        result = ResearchService(get_request_workspace(request)).search(session.session_id, body.query, provider)
        artifact = {
            "type": "web_candidates",
            "artifact_id": uuid.uuid4().hex,
            "search_id": result["search_id"],
            "status": "ready" if result["candidates"] else "failed",
            "query": result["query"],
            "provider": result["provider"],
            "candidates": [
                {
                    "candidate_id": item["candidate_id"], "title": item["title"], "url": item["url"],
                    "domain": item["domain"], "snippet": item.get("snippet", ""),
                    "published_at": item.get("published_at"), "rank": item.get("rank", 0),
                    "provider": item["provider"], "quality_hint": item["quality_hint"],
                }
                for item in result["candidates"]
            ],
        }
    except SearchProviderError as exc:
        artifact = {
            "type": "web_candidates", "artifact_id": uuid.uuid4().hex, "search_id": "",
            "status": "failed", "query": body.query.strip(), "provider": provider,
            "candidates": [], "error_kind": exc.kind,
        }
    except Exception:
        artifact = {
            "type": "web_candidates", "artifact_id": uuid.uuid4().hex, "search_id": "",
            "status": "failed", "query": body.query.strip(), "provider": provider,
            "candidates": [], "error_kind": "network",
        }
    _append_artifact(session, "已整理联网候选来源，请选择需要读取的网页。" if artifact["candidates"] else "联网搜索暂时没有返回可用来源。", artifact)
    _save_session(request, session)
    return {"ok": True, "chat_session_id": session.session_id, "artifact": artifact}


@router.post("/consents/{artifact_id}/reject")
def reject_consent(artifact_id: str, body: WebConsentRejectRequest, request: Request) -> dict:
    session = _load_session(request, body.chat_session_id)
    artifact = _find_artifact(session, artifact_id, "web_consent")
    if not artifact:
        raise APIError(404, "web_consent_not_found", "The web search confirmation is no longer available.")
    if artifact.get("status") != "pending":
        raise APIError(409, "web_consent_resolved", "The web search confirmation has already been handled.")
    artifact["status"] = "rejected"
    _save_session(request, session)
    return {"ok": True, "artifact": artifact}


@router.post("/searches/{search_id}/select")
def select_sources(search_id: str, body: WebSourceSelectRequest, request: Request) -> dict:
    session = _load_session(request, body.chat_session_id)
    artifact = next((
        item for message in session.messages for item in message.get("artifacts") or []
        if item.get("type") == "web_candidates" and item.get("search_id") == search_id
    ), None)
    if not artifact:
        raise APIError(404, "web_search_not_found", "The web source candidates are no longer available.")
    retryable_failure = artifact.get("status") == "failed" and bool(artifact.get("candidates"))
    if artifact.get("status") not in {"ready", "partial"} and not retryable_failure:
        raise APIError(409, "web_search_not_selectable", "The web source candidates cannot be selected now.")
    artifact["status"] = "fetching"
    preferences = _preferences()
    try:
        result = ResearchService(get_request_workspace(request)).select(
            search_id,
            session.session_id,
            body.candidate_ids,
            jina_fallback=bool(preferences.get("search", {}).get("jina_fallback", True)),
        )
    except FileNotFoundError as exc:
        raise APIError(404, "web_search_not_found", str(exc)) from exc
    except ValueError as exc:
        raise APIError(422, "invalid_web_source_selection", str(exc)) from exc
    artifact["status"] = "used" if result["status"] == "ready" else result["status"]
    evidence = {
        "type": "web_evidence", "artifact_id": uuid.uuid4().hex,
        "research_id": result["research_id"], "status": result["status"],
        "sources": result["sources"], "failed_source_ids": result["failed_source_ids"],
    }
    _append_artifact(
        session,
        "选中的网页证据已经准备好，可以继续回答。" if result["sources"] else "选中的网页暂时无法读取。",
        evidence,
    )
    _save_session(request, session)
    return {"ok": True, "chat_session_id": session.session_id, "artifact": evidence}


@router.get("/sources/{snapshot_id}")
def source_detail(snapshot_id: str, request: Request) -> dict:
    try:
        return {"ok": True, "source": ResearchService(get_request_workspace(request)).source(snapshot_id)}
    except FileNotFoundError as exc:
        raise APIError(404, "web_source_not_found", str(exc)) from exc
