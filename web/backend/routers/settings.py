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
from service.research_service import ResearchService
from service.usage_service import UsageService
from web.backend.capabilities import WEB_SKILL_NAMES
from web.backend.deps import (
    get_config,
    get_default_provider_name,
    get_request_library_id,
    get_request_workspace,
    get_session_save_dir,
    get_workspace,
    reset_dependency_caches,
)
from web.backend.errors import APIError

router = APIRouter()


class PreferencesPatchRequest(BaseModel):
    revision: int = Field(..., ge=0)
    patch: dict[str, Any]


class ProviderUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    base_url: str = Field(..., min_length=1, max_length=300)
    type: str = Field(default="openai_compatible", min_length=1, max_length=40)
    provider_name: str | None = None
    preset: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    model_default: str | None = None
    models: list[dict[str, str]] = Field(default_factory=list, max_length=200)


class ProviderFetchModelsRequest(BaseModel):
    base_url: str = Field(..., min_length=1, max_length=300)
    api_key: str | None = None


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
        "search_providers": [
            {"name": "auto", "configured": True},
            {"name": "tavily", "configured": bool(os.getenv("TAVILY_API_KEY"))},
            {"name": "exa", "configured": True},
        ],
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


@router.get("/providers/presets")
def provider_presets() -> dict:
    """内建模板（P5G.4）：预设供应商 + Ollama，供「添加供应商」使用。"""
    from providers.catalog import BUILTIN_PRESETS

    return {
        "ok": True,
        "presets": [
            {
                "name": name,
                "type": raw.get("type", "openai_compatible"),
                "provider_name": raw.get("provider_name", name),
                "base_url": raw.get("base_url", ""),
                "api_key_env": raw.get("api_key_env", ""),
            }
            for name, raw in sorted(BUILTIN_PRESETS.items())
        ],
    }


@router.put("/providers")
def upsert_provider(body: ProviderUpsertRequest) -> dict:
    """新增或编辑供应商（P5G.4）。api_key 留空 = 保持原 key。"""
    from providers.catalog import upsert_provider as catalog_upsert

    if body.name in ("auto", "default"):
        raise APIError(422, "invalid_provider_name", "This name is reserved.")
    entry = {
        "type": body.type,
        "provider_name": body.provider_name or body.preset or body.name,
        "preset": body.preset or "",
        "base_url": body.base_url,
        "api_key": body.api_key or "",
        "api_key_env": body.api_key_env or "",
        "model_default": body.model_default or "",
        "models": body.models or [],
    }
    catalog_upsert(body.name, entry)
    reset_dependency_caches()
    return {"ok": True, "name": body.name}


@router.delete("/providers/{provider_name}")
def remove_provider(provider_name: str) -> dict:
    """删除供应商（P5G.4）。"""
    from providers.catalog import delete_provider as catalog_delete

    if not catalog_delete(provider_name):
        raise APIError(404, "provider_not_found", "The provider does not exist.")
    reset_dependency_caches()
    return {"ok": True, "name": provider_name}


@router.post("/providers/fetch-models")
def fetch_provider_models(body: ProviderFetchModelsRequest) -> dict:
    """远程拉取模型列表（GET {base}/models，OpenAI 兼容协议，P5G.4）。

    失败返回 409，由前端提示手输兜底。
    """
    import httpx

    base_url = body.base_url.rstrip("/")
    headers = {}
    if body.api_key:
        headers["Authorization"] = f"Bearer {body.api_key}"
    try:
        response = httpx.get(f"{base_url}/models", headers=headers, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException:
        raise APIError(409, "fetch_models_timeout", "The provider did not respond in time.")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401 or exc.response.status_code == 403:
            raise APIError(409, "fetch_models_unauthorized", "The API key was rejected.")
        raise APIError(409, "fetch_models_failed", "The provider could not be reached.")
    except (httpx.HTTPError, ValueError):
        raise APIError(409, "fetch_models_failed", "The provider could not be reached.")

    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        items = payload.get("models", []) if isinstance(payload, dict) else []
    models = sorted(
        ({"id": item.get("id") or item.get("name", ""), "name": item.get("id") or item.get("name", "")}
         for item in items if isinstance(item, dict) and (item.get("id") or item.get("name"))),
        key=lambda item: item["id"],
    )
    return {"ok": True, "models": models}


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


@router.post("/search/{provider_name}/test")
def test_search_provider(provider_name: Literal["auto", "tavily", "exa"], request: Request) -> dict:
    started = time.perf_counter()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(ResearchService(get_request_workspace(request)).test, provider_name)
        result = future.result(timeout=20)
        return {**result, "latency_ms": round((time.perf_counter() - started) * 1000)}
    except FutureTimeout as exc:
        raise APIError(504, "search_provider_timeout", "The search provider did not respond within 20 seconds.") from exc
    except Exception as exc:
        kind = getattr(exc, "kind", "network")
        raise APIError(409, "search_provider_test_failed", "The search provider connection test failed.", {"kind": kind}) from exc
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
        "search": {
            "default": preferences.get("search", {}).get("provider", "auto"),
            "permission": preferences.get("search", {}).get("permission", "ask"),
            "tavily_configured": bool(os.getenv("TAVILY_API_KEY")),
            "exa_configured": True,
            "jina_fallback": bool(preferences.get("search", {}).get("jina_fallback", True)),
        },
    }


@router.get("/usage")
def llm_usage(days: int = 7) -> dict:
    return {"ok": True, **UsageService().summary(days=max(1, min(days, 30)))}


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
