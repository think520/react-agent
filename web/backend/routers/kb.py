"""Knowledge base and managed library endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel, Field

from service.kb_service import KBService
from service.preference_service import PreferenceService
from web.backend.capabilities import WEB_SKILL_NAMES
from web.backend.deps import (
    get_config, get_default_provider_name, get_library_runtime_context, get_request_workspace,
    get_runtime_context, get_workspace,
)
from web.backend.errors import APIError, unwrap_service_result

router = APIRouter()

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class KBSyncRequest(BaseModel):
    vault_path: str
    course_dir: str | None = None
    mode: str = "incremental"


class KBSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    course: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = "auto"


class GraphQueryRequest(BaseModel):
    concept: str = Field(..., min_length=1)
    intent: str = "related"
    limit: int = Field(default=20, ge=1, le=50)


class WikiMaintenanceRequest(BaseModel):
    action: str


class WikiSemanticReviewRequest(BaseModel):
    provider: str | None = None


class WikiTaskRetryRequest(BaseModel):
    provider: str | None = None


class WikiPlanRequest(BaseModel):
    action: Literal["generate", "update"] = "generate"
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    wiki_document_ids: list[str] = Field(default_factory=list, max_length=20)
    course: str | None = None
    instruction: str = Field(default="", max_length=1000)
    provider: str | None = None


class WikiPlanRecoveryRequest(BaseModel):
    strategy: Literal["keep_existing", "regenerate"]
    provider: str | None = None


class WikiRunRequest(BaseModel):
    action: Literal["generate", "update"] = "generate"
    scope_mode: Literal["uncovered", "smart_library", "selected_only", "course"] = "uncovered"
    document_ids: list[str] = Field(default_factory=list, max_length=500)
    course: str | None = None
    topic: str = Field(default="", max_length=500)
    instruction: str = Field(default="", max_length=1000)
    provider: str | None = None


def _service(request: Request) -> KBService:
    return KBService(get_request_workspace(request))


def _runtime_for(workspace: str):
    if workspace == get_workspace():
        return get_runtime_context()
    return get_library_runtime_context(workspace)


def _preferred_provider(requested: str | None) -> str | None:
    if requested:
        return requested
    config = get_config()
    return PreferenceService(
        get_default_provider_name(config),
        sorted(WEB_SKILL_NAMES),
    ).get().get("ai", {}).get("default_provider")


def _public_sync(result: dict) -> dict:
    public = {
        key: value for key, value in result.items()
        if key not in {"rag_index_path", "graph_store_path"}
    }
    public["errors"] = [
        {
            "source": item.get("source", ""),
            "error": "This file could not be indexed.",
        }
        for item in public.get("errors", [])
    ]
    return public


@router.get("/status")
def status(request: Request) -> dict:
    result = _service(request).status()
    if not result.get("ok"):
        raise APIError(404, "knowledge_base_not_found", result["error"])
    return result


@router.post("/sync")
def sync(body: KBSyncRequest, request: Request) -> dict:
    result = unwrap_service_result(_service(request).sync(
        vault_path=body.vault_path,
        course_dir=body.course_dir,
        mode=body.mode,
        config=get_config(),
    ))
    return _public_sync(result)


@router.post("/import")
async def import_files(request: Request, files: list[UploadFile] = File(...)) -> dict:
    payload = []
    for upload in files:
        content = await upload.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            raise APIError(
                413,
                "file_too_large",
                f"File exceeds 25 MB limit: {upload.filename or '(unnamed)'}",
            )
        payload.append((upload.filename or "", content))
    result = unwrap_service_result(_service(request).import_files(payload, config=get_config()))
    result["sync"] = _public_sync(result["sync"])
    return result


@router.get("/documents")
def documents(request: Request, course: str | None = None, collection: str = "all") -> dict:
    return unwrap_service_result(_service(request).list_documents(
        course=course,
        collection=collection,
    ))


@router.get("/wiki/maintenance")
def wiki_maintenance_status(request: Request) -> dict:
    return unwrap_service_result(_service(request).wiki_health())


@router.get("/wiki/coverage")
def wiki_document_coverage(request: Request) -> dict:
    return unwrap_service_result(_service(request).wiki_coverage())


@router.post("/wiki/maintenance")
def maintain_wiki(body: WikiMaintenanceRequest, request: Request) -> dict:
    return unwrap_service_result(_service(request).maintain_wiki(body.action))


@router.post("/wiki/maintenance/semantic")
def semantic_wiki_review(body: WikiSemanticReviewRequest, request: Request) -> dict:
    workspace = get_request_workspace(request)
    try:
        provider = _runtime_for(workspace).create_provider(_preferred_provider(body.provider))
    except ValueError as exc:
        raise APIError(409, "provider_unavailable", str(exc)) from exc
    return unwrap_service_result(
        _service(request).review_wiki_semantics(provider),
        code="wiki_semantic_review_failed",
    )


@router.post("/wiki/plans")
def create_wiki_plan(body: WikiPlanRequest, request: Request) -> dict:
    workspace = get_request_workspace(request)
    try:
        provider = _runtime_for(workspace).create_provider(_preferred_provider(body.provider))
    except ValueError as exc:
        raise APIError(409, "provider_unavailable", str(exc)) from exc
    return unwrap_service_result(
        _service(request).create_wiki_plan(
            provider,
            document_ids=body.document_ids,
            wiki_document_ids=body.wiki_document_ids,
            course=body.course,
            action=body.action,
            instruction=body.instruction,
        ),
        code="wiki_plan_failed",
    )


@router.post("/wiki/migrations/preview")
def preview_wiki_migration(request: Request) -> dict:
    return unwrap_service_result(
        _service(request).create_wiki_migration_plan(),
        code="wiki_migration_preview_failed",
    )


@router.get("/wiki/plans/{plan_id}")
def wiki_plan(plan_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).get_wiki_plan(plan_id),
        status_code=404,
        code="wiki_plan_not_found",
    )


@router.post("/wiki/plans/{plan_id}/apply")
def apply_wiki_plan(plan_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).apply_wiki_plan(plan_id, config=get_config()),
        status_code=409,
        code="wiki_plan_not_applicable",
    )


@router.post("/wiki/plans/{plan_id}/recover")
def recover_wiki_plan(plan_id: str, body: WikiPlanRecoveryRequest, request: Request) -> dict:
    workspace = get_request_workspace(request)
    provider = None
    if body.strategy == "regenerate":
        try:
            provider = _runtime_for(workspace).create_provider(_preferred_provider(body.provider))
        except ValueError as exc:
            raise APIError(409, "provider_unavailable", str(exc)) from exc
    return unwrap_service_result(
        _service(request).recover_wiki_plan(
            plan_id,
            body.strategy,
            llm_provider=provider,
            config=get_config(),
        ),
        status_code=409,
        code="wiki_plan_recovery_failed",
    )


@router.post("/wiki/runs")
def create_wiki_run(body: WikiRunRequest, request: Request) -> dict:
    workspace = get_request_workspace(request)
    try:
        provider = _runtime_for(workspace).create_provider(_preferred_provider(body.provider))
    except ValueError as exc:
        raise APIError(409, "provider_unavailable", str(exc)) from exc
    return unwrap_service_result(
        _service(request).start_wiki_run(
            provider,
            action=body.action,
            scope_mode=body.scope_mode,
            document_ids=body.document_ids,
            course=body.course,
            topic=body.topic,
            instruction=body.instruction,
            config=get_config(),
        ),
        status_code=409,
        code="wiki_run_failed",
    )


@router.get("/wiki/runs/{run_id}")
def get_wiki_run(run_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).get_wiki_run(run_id),
        status_code=404,
        code="wiki_run_not_found",
    )


@router.post("/wiki/checkpoints/{checkpoint_id}/restore")
def restore_wiki_checkpoint(checkpoint_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).undo_wiki_checkpoint(checkpoint_id, config=get_config()),
        status_code=409,
        code="wiki_checkpoint_not_restorable",
    )


@router.get("/wiki/tasks")
def wiki_tasks(request: Request) -> dict:
    return unwrap_service_result(_service(request).wiki_tasks())


@router.post("/wiki/tasks/{task_id}/cancel")
def cancel_wiki_task(task_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).cancel_wiki_task(task_id),
        status_code=409,
        code="wiki_task_not_cancellable",
    )


@router.post("/wiki/tasks/{task_id}/retry")
def retry_wiki_task(task_id: str, body: WikiTaskRetryRequest, request: Request) -> dict:
    workspace = get_request_workspace(request)
    service = _service(request)
    task = next((item for item in service.wiki_tasks().get("tasks", []) if item.get("task_id") == task_id), None)
    provider = None
    if task and task.get("operation") in {"plan", "orchestrate"}:
        try:
            provider = _runtime_for(workspace).create_provider(_preferred_provider(body.provider))
        except ValueError as exc:
            raise APIError(409, "provider_unavailable", str(exc)) from exc
    return unwrap_service_result(
        service.retry_wiki_task(task_id, provider, config=get_config()),
        status_code=409,
        code="wiki_task_not_retryable",
    )


@router.get("/documents/{document_id}")
def document_detail(document_id: str, request: Request) -> dict:
    result = _service(request).get_document(document_id)
    if not result.get("ok"):
        raise APIError(404, "document_not_found", result["error"])
    return result


@router.get("/documents/{document_id}/impact")
def document_impact(document_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).document_impact(document_id),
        status_code=404,
        code="document_not_found",
    )


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, request: Request) -> dict:
    result = _service(request).delete_document(document_id, config=get_config())
    if not result.get("ok"):
        message = result["error"]
        status_code = 409 if "read-only" in message else 404
        raise APIError(status_code, "document_not_deletable", message)
    result["sync"] = _public_sync(result["sync"])
    return result


@router.post("/search")
def search(body: KBSearchRequest, request: Request) -> dict:
    return unwrap_service_result(_service(request).search(
        query=body.query,
        course=body.course,
        top_k=body.top_k,
        mode=body.mode,
        config=get_config(),
    ))


@router.post("/graph")
def graph_query(body: GraphQueryRequest, request: Request) -> dict:
    return unwrap_service_result(_service(request).graph_query(
        concept=body.concept,
        intent=body.intent,
        limit=body.limit,
    ))
