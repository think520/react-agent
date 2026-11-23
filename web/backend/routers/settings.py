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
    models: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


class ProviderFetchModelsRequest(BaseModel):
    base_url: str = Field(..., min_length=1, max_length=300)
    api_key: str | None = None
    provider_name: str | None = Field(default=None, max_length=80)


class RagSettingsUpdateRequest(BaseModel):
    mode: Literal["auto", "provider", "custom", "ollama", "disabled"]
    provider_name: str = Field(default="", max_length=80)
    preset: str = Field(default="", max_length=40)
    base_url: str = Field(default="", max_length=300)
    model: str = Field(default="", max_length=120)
    api_key: str = Field(default="", max_length=300)
    clear_api_key: bool = False
    dim: int | None = Field(default=None, ge=1, le=16384)
    ollama_url: str = Field(default="http://localhost:11434", max_length=300)
    ollama_model: str = Field(default="qwen3-embedding:0.6b", max_length=120)


class RagEmbeddingTestRequest(BaseModel):
    mode: Literal["auto", "provider", "custom", "ollama", "disabled"] | None = None
    provider_name: str = Field(default="", max_length=80)
    preset: str = Field(default="", max_length=40)
    base_url: str = Field(default="", max_length=300)
    model: str = Field(default="", max_length=120)
    api_key: str = Field(default="", max_length=300)
    dim: int | None = Field(default=None, ge=1, le=16384)
    ollama_url: str = Field(default="http://localhost:11434", max_length=300)
    ollama_model: str = Field(default="qwen3-embedding:0.6b", max_length=120)


class RagBackfillRequest(BaseModel):
    rebuild: bool = False


class RagSearchTestRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=300)
    top_k: int = Field(default=5, ge=1, le=10)
    mode: Literal["auto", "hybrid", "directory", "directory_grep"] = "auto"


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
                "model_default": raw.get("model_default", ""),
                "models": raw.get("models", []),
                "auth_type": raw.get("auth_type", "api-key"),
                "keyless": bool(raw.get("keyless")),
                "supports_embedding": raw.get("supports_embedding"),
                "embedding_note": raw.get("embedding_note", ""),
                "note": raw.get("note", ""),
            }
            for name, raw in sorted(BUILTIN_PRESETS.items())
        ],
    }


@router.put("/providers")
def upsert_provider(body: ProviderUpsertRequest) -> dict:
    """新增或编辑供应商（P5G.4）。api_key 留空 = 保持原 key。"""
    from providers.catalog import upsert_provider as catalog_upsert
    from rag.retriever import clear_retrieval_cache

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
    clear_retrieval_cache()
    return {"ok": True, "name": body.name}


@router.delete("/providers/{provider_name}")
def remove_provider(provider_name: str) -> dict:
    """删除供应商（P5G.4）。"""
    from providers.catalog import delete_provider as catalog_delete
    from rag.retriever import clear_retrieval_cache

    if not catalog_delete(provider_name):
        raise APIError(404, "provider_not_found", "The provider does not exist.")
    reset_dependency_caches()
    clear_retrieval_cache()
    return {"ok": True, "name": provider_name}


@router.post("/providers/fetch-models")
def fetch_provider_models(body: ProviderFetchModelsRequest) -> dict:
    """远程拉取模型列表（GET {base}/models，OpenAI 兼容协议，P5G.4）。

    失败返回 409，由前端提示手输兜底。
    """
    import httpx
    from urllib.parse import urlparse
    from providers.catalog import classify_model_kind, load_catalog, resolve_api_key

    base_url = body.base_url.rstrip("/")
    resolved_key = (body.api_key or "").strip()
    if not resolved_key and body.provider_name:
        saved = load_catalog().get("providers", {}).get(body.provider_name.strip())
        if isinstance(saved, dict):
            saved_url = str(saved.get("base_url") or "").strip()
            req_parsed = urlparse(base_url)
            saved_parsed = urlparse(saved_url)
            if (
                req_parsed.scheme
                and req_parsed.netloc
                and req_parsed.scheme.lower() == saved_parsed.scheme.lower()
                and req_parsed.netloc.lower() == saved_parsed.netloc.lower()
            ):
                resolved_key = resolve_api_key(saved)
    headers = {}
    if resolved_key:
        headers["Authorization"] = f"Bearer {resolved_key}"
    try:
        response = httpx.get(f"{base_url}/models", headers=headers, timeout=10)
        response.raise_for_status()
    except httpx.TimeoutException:
        raise APIError(409, "fetch_models_timeout", "读取模型超时，请检查网络连接或稍后重试。")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401 or exc.response.status_code == 403:
            raise APIError(409, "fetch_models_unauthorized", "API Key 未通过验证，请检查密钥是否正确。")
        if exc.response.status_code in {404, 405}:
            raise APIError(
                409,
                "fetch_models_endpoint_unsupported",
                "该服务没有提供可用的 GET /models 接口。请确认 API 地址填写到服务根路径（例如 /v1），或手动添加服务商给出的模型 ID。",
            )
        if exc.response.status_code == 429:
            raise APIError(409, "fetch_models_rate_limited", "读取模型请求过于频繁，请稍后重试。")
        raise APIError(
            409,
            "fetch_models_http_error",
            f"模型列表接口返回 HTTP {exc.response.status_code}。请检查 API 地址和密钥，或手动添加模型 ID。",
        )
    except httpx.HTTPError:
        raise APIError(409, "fetch_models_failed", "无法连接到模型服务，请检查 API 地址和网络连接。")

    try:
        payload = response.json()
    except ValueError:
        raise APIError(
            409,
            "fetch_models_unsupported_format",
            "服务返回的不是有效的 JSON 模型列表。请确认 API 地址填写到服务根路径（例如 /v1），或手动添加准确的模型 ID。",
        )

    items = payload if isinstance(payload, list) else None
    if isinstance(payload, dict):
        for key in ("data", "models"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break
    if items is None:
        raise APIError(
            409,
            "fetch_models_unsupported_format",
            "服务返回的模型列表格式无法识别。请核对服务商文档，或手动添加准确的模型 ID。",
        )

    models_by_id = {}
    for item in items:
        if isinstance(item, str):
            model_id = item.strip()
            model_name = model_id
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("model") or item.get("model_id") or item.get("name") or "").strip()
            model_name = str(item.get("name") or model_id).strip()
        else:
            continue
        if model_id:
            existing = models_by_id.get(model_id)
            kind = classify_model_kind(model_id)
            if existing is None or (existing["name"] == model_id and model_name and model_name != model_id):
                entry: dict[str, str] = {"id": model_id, "name": model_name or model_id}
                if kind != "chat":
                    entry["kind"] = kind
                models_by_id[model_id] = entry
    models = sorted(models_by_id.values(), key=lambda item: item["id"])
    if items and not models:
        raise APIError(
            409,
            "fetch_models_unsupported_format",
            "服务返回了模型列表，但其中没有可识别的模型 ID。请手动添加服务商提供的模型 ID。",
        )
    if not models:
        raise APIError(
            409,
            "fetch_models_empty",
            "接口可访问，但没有返回可用模型。请确认账号权限，或手动添加服务商提供的模型 ID。",
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
    from service.rag_settings_service import RagSettingsService

    config = get_config()
    preferences = _service(config).get()
    registry = LibraryService().list_libraries()
    active = next((item for item in registry.get("libraries", []) if item.get("active")), None)
    knowledge = {"state": "not_selected", "documents": 0}
    active_workspace: str | None = None
    if active and active.get("available"):
        active_workspace = LibraryService().resolve(active["library_id"])["path"]
        result = KBService(active_workspace).status()
        knowledge = {
            "state": "ready" if result.get("ok") else "empty",
            "documents": int(result.get("total_files") or 0),
        }
    providers = AgentService.list_providers(config)["providers"]
    retrieval_summary = RagSettingsService.get_summary(config, active_workspace)
    return {
        "ok": True,
        "backend": "connected",
        "version": "0.1.0",
        "active_library": active,
        "knowledge": knowledge,
        "retrieval": {
            "effective_mode": retrieval_summary["effective_mode"],
            "embedding_available": retrieval_summary["embedding_available"],
            "active_provider": retrieval_summary["display_provider"] or retrieval_summary["active_provider"],
            "active_model": retrieval_summary["active_model"],
            "vector_indexed": retrieval_summary["vector_stats"]["vector_indexed"],
            "documents": retrieval_summary["vector_stats"]["documents"],
        },
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


@router.get("/rag")
def rag_settings(request: Request) -> dict:
    from service.rag_settings_service import RagSettingsService

    config = get_config()
    workspace = get_request_workspace(request)
    return RagSettingsService.get_settings(config, workspace)


@router.put("/rag")
def update_rag_settings(body: RagSettingsUpdateRequest, request: Request) -> dict:
    from providers.catalog import save_embedding_config
    from rag.retriever import clear_retrieval_cache
    from service.rag_settings_service import RagSettingsService

    try:
        save_embedding_config(
            body.model_dump(exclude={"clear_api_key"}),
            clear_api_key=body.clear_api_key,
        )
    except ValueError as exc:
        raise APIError(422, "invalid_rag_config", str(exc)) from exc
    reset_dependency_caches()
    clear_retrieval_cache()
    config = get_config()
    workspace = get_request_workspace(request)
    return RagSettingsService.get_settings(config, workspace)


@router.post("/rag/test")
def test_rag_embedding(body: RagEmbeddingTestRequest | None = None) -> dict:
    from service.rag_settings_service import RagSettingsService

    config = get_config()
    payload = body.model_dump() if body and body.mode is not None else None
    try:
        return RagSettingsService.test_embedding(payload, config)
    except ValueError as exc:
        raise APIError(422, "invalid_rag_test_config", str(exc)) from exc
    except TimeoutError as exc:
        raise APIError(504, "embedding_test_timeout", str(exc)) from exc
    except Exception as exc:
        raise APIError(409, "embedding_test_failed", str(exc)) from exc


@router.post("/rag/backfill")
def backfill_rag_vectors(request: Request, body: RagBackfillRequest | None = None) -> dict:
    from service.rag_settings_service import RagSettingsService

    config = get_config()
    workspace = get_request_workspace(request)
    try:
        result = RagSettingsService.backfill_vectors(
            workspace,
            config,
            rebuild=bool(body.rebuild if body else False),
        )
    except ValueError as exc:
        raise APIError(422, "rag_backfill_invalid", str(exc)) from exc
    except Exception as exc:
        raise APIError(409, "rag_backfill_failed", str(exc)) from exc
    return {
        "ok": True,
        "result": result,
        "rag": RagSettingsService.get_settings(config, workspace),
    }


@router.post("/rag/search-test")
def test_rag_search(body: RagSearchTestRequest, request: Request) -> dict:
    from service.rag_settings_service import RagSettingsService

    config = get_config()
    workspace = get_request_workspace(request)
    try:
        return RagSettingsService.search_test(
            workspace,
            config,
            query=body.query,
            top_k=body.top_k,
            mode=body.mode,
        )
    except ValueError as exc:
        raise APIError(422, "invalid_search_test", str(exc)) from exc
    except Exception as exc:
        raise APIError(409, "search_test_failed", str(exc)) from exc


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
