"""User preferences, provider checks, and lightweight runtime status."""

from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core.session import Session
from core.skills import list_skills
from service.agent_service import AgentService
from service.kb_service import KBService
from service.library_service import LibraryService
from service.preference_service import PreferenceService
from service.runtime_service import RuntimeService
from web.backend.capabilities import WEB_SKILL_NAMES
from web.backend.deps import (
    get_config,
    get_default_provider_name,
    get_request_library_id,
    get_request_workspace,
    get_session_save_dir,
    get_workspace,
)
from web.backend.errors import APIError

router = APIRouter()


class PreferencesPatchRequest(BaseModel):
    revision: int = Field(..., ge=0)
    patch: dict[str, Any]


class SettingsProposalRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    chat_session_id: str | None = None


class SettingsProposalResolveRequest(BaseModel):
    chat_session_id: str
    action: Literal["apply", "reject"]


class SettingsProposalActionRequest(BaseModel):
    chat_session_id: str


def _skills(config: dict[str, Any]) -> list:
    skills_config = config.get("skills", {})
    if not skills_config.get("enabled", True):
        return []
    skills_dir = skills_config.get("dir", "skills")
    if not os.path.isabs(skills_dir):
        skills_dir = os.path.join(get_workspace(), skills_dir)
    return [skill for skill in list_skills(skills_dir) if skill.name in WEB_SKILL_NAMES]


def _service(config: dict[str, Any]) -> PreferenceService:
    return PreferenceService(
        get_default_provider_name(config),
        [skill.name for skill in _skills(config)],
    )


def _provider_names(config: dict[str, Any]) -> set[str]:
    return set((config.get("llm", {}).get("providers") or {}).keys())


def _configured_provider_names(config: dict[str, Any]) -> set[str]:
    return {
        item["name"]
        for item in AgentService.list_providers(config)["providers"]
        if item.get("configured")
    }


def _public_settings(config: dict[str, Any]) -> dict[str, Any]:
    skills = _skills(config)
    preferences = _service(config).get()
    enabled = set(preferences["skills"]["enabled_names"])
    providers = AgentService.list_providers(config)["providers"]
    return {
        "ok": True,
        "workspace_name": os.path.basename(get_workspace()),
        "default_provider": preferences["ai"]["default_provider"],
        "providers": providers,
        "mcp_enabled": bool(config.get("mcp", {}).get("enabled", False)),
        "preferences": preferences,
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "enabled": skill.name in enabled,
                "source": "built-in",
                "capabilities": ["学习对话", "资料理解"],
            }
            for skill in skills
        ],
    }


@router.get("")
def settings() -> dict:
    return _public_settings(get_config())


@router.patch("/preferences")
def patch_preferences(body: PreferencesPatchRequest) -> dict:
    config = get_config()
    skills = {skill.name for skill in _skills(config)}
    try:
        preferences = _service(config).patch(
            body.revision,
            body.patch,
            _configured_provider_names(config),
            skills,
        )
    except RuntimeError as exc:
        raise APIError(409, "preferences_revision_conflict", "Settings changed in another view. Reload and try again.") from exc
    except ValueError as exc:
        raise APIError(422, "invalid_preference", str(exc)) from exc
    return {"ok": True, "preferences": preferences}


@router.post("/providers/{provider_name}/test")
def test_provider(provider_name: str) -> dict:
    config = get_config()
    if provider_name not in _provider_names(config):
        raise APIError(404, "provider_not_found", "The selected provider does not exist.")
    started = time.perf_counter()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        provider = RuntimeService.create_provider(config, provider_name)
        future = executor.submit(provider.complete, [{"role": "user", "content": "Reply with OK only."}])
        response = future.result(timeout=10)
        latency_ms = round((time.perf_counter() - started) * 1000)
        model = next(
            (item.get("model") for item in AgentService.list_providers(config)["providers"] if item["name"] == provider_name),
            "",
        )
        return {
            "ok": True,
            "provider": provider_name,
            "model": model,
            "latency_ms": latency_ms,
            "response_received": bool(getattr(response, "content", "")),
        }
    except FutureTimeout as exc:
        raise APIError(504, "provider_timeout", "The provider did not respond within 10 seconds.") from exc
    except Exception as exc:
        message = str(exc).lower()
        kind = "authentication" if any(token in message for token in ("401", "unauthorized", "api key")) else "network"
        raise APIError(409, "provider_test_failed", "The provider connection test failed.", {"kind": kind}) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


@router.get("/status")
def runtime_status() -> dict:
    config = get_config()
    preferences = _service(config).get()
    registry = LibraryService().list_libraries()
    active = next((item for item in registry.get("libraries", []) if item.get("active")), None)
    knowledge = {"state": "not_selected", "documents": 0}
    if active and active.get("available"):
        result = KBService(LibraryService().resolve(active["library_id"])["path"]).status()
        knowledge = {
            "state": "ready" if result.get("ok") else "empty",
            "documents": int(result.get("total_files") or 0),
        }
    providers = AgentService.list_providers(config)["providers"]
    return {
        "ok": True,
        "backend": "connected",
        "version": "0.1.0",
        "active_library": active,
        "knowledge": knowledge,
        "memory": {"enabled": preferences["memory"]["enabled"]},
        "skills": {
            "enabled": len(preferences["skills"]["enabled_names"]),
            "available": len(_skills(config)),
        },
        "providers": {
            "configured": sum(bool(item.get("configured")) for item in providers),
            "available": len(providers),
            "default": preferences["ai"]["default_provider"],
        },
    }


def _load_or_create_session(request: Request, chat_session_id: str | None) -> Session:
    config = get_config()
    workspace = get_request_workspace(request)
    library_id = get_request_library_id(request)
    save_dir = get_session_save_dir(config, workspace)
    if chat_session_id:
        result = AgentService.load_session(chat_session_id, save_dir)
        if not result.get("ok"):
            raise APIError(404, "session_not_found", result.get("error") or "Session not found")
        session = result["session"]
        if session.library_id and session.library_id != library_id:
            raise APIError(404, "session_not_found", "Session not found in this library")
    else:
        session = Session.new(workspace, max_messages=config.get("session", {}).get("max_messages"))
    session.library_id = library_id
    return session


def _save_session(request: Request, session: Session) -> None:
    result = AgentService.save_session(session, get_session_save_dir(get_config(), get_request_workspace(request)))
    if not result.get("ok"):
        raise APIError(500, "session_save_failed", "The settings conversation could not be saved.")


def _update_proposal_artifact(session: Session, proposal_id: str, status: str) -> None:
    for message in session.messages:
        for artifact in message.get("artifacts") or []:
            if artifact.get("type") == "settings_change" and artifact.get("proposal_id") == proposal_id:
                artifact["status"] = status


@router.post("/proposals")
def create_settings_proposal(body: SettingsProposalRequest, request: Request) -> dict:
    config = get_config()
    proposal = _service(config).create_proposal(body.message)
    if proposal is None:
        raise APIError(409, "settings_change_not_detected", "No supported settings change was found.")
    session = _load_or_create_session(request, body.chat_session_id)
    session.messages.append({"role": "user", "content": body.message})
    artifact = {
        "artifact_id": uuid.uuid4().hex,
        "type": "settings_change",
        "proposal_id": proposal["proposal_id"],
        "status": proposal["status"],
        "changes": proposal["changes"],
    }
    session.messages.append({
        "role": "assistant",
        "content": "我可以按下面的方式调整设置。确认前不会修改。",
        "artifacts": [artifact],
    })
    session.last_active = datetime.now().isoformat()
    session._trim_messages()
    _save_session(request, session)
    return {"ok": True, "chat_session_id": session.session_id, "artifact": artifact}


@router.post("/proposals/{proposal_id}/resolve")
def resolve_settings_proposal(
    proposal_id: str,
    body: SettingsProposalResolveRequest,
    request: Request,
) -> dict:
    config = get_config()
    try:
        proposal, preferences = _service(config).resolve_proposal(
            proposal_id,
            body.action,
            _configured_provider_names(config),
            {skill.name for skill in _skills(config)},
        )
    except FileNotFoundError as exc:
        raise APIError(404, "settings_proposal_not_found", str(exc)) from exc
    except RuntimeError as exc:
        raise APIError(409, "preferences_revision_conflict", "Settings changed since this proposal was created.") from exc
    except ValueError as exc:
        raise APIError(409, "settings_proposal_not_applicable", str(exc)) from exc
    session = _load_or_create_session(request, body.chat_session_id)
    _update_proposal_artifact(session, proposal_id, proposal["status"])
    _save_session(request, session)
    return {"ok": True, "proposal": proposal, "preferences": preferences}


@router.post("/proposals/{proposal_id}/apply")
def apply_settings_proposal(
    proposal_id: str,
    body: SettingsProposalActionRequest,
    request: Request,
) -> dict:
    return resolve_settings_proposal(
        proposal_id,
        SettingsProposalResolveRequest(chat_session_id=body.chat_session_id, action="apply"),
        request,
    )


@router.post("/proposals/{proposal_id}/reject")
def reject_settings_proposal(
    proposal_id: str,
    body: SettingsProposalActionRequest,
    request: Request,
) -> dict:
    return resolve_settings_proposal(
        proposal_id,
        SettingsProposalResolveRequest(chat_session_id=body.chat_session_id, action="reject"),
        request,
    )
