"""Knowledge base and managed library endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel, Field

from service.kb_service import KBService
from service.concept_service import ConceptService
from service.document_edit_service import DocumentEditService
from service.document_proposal_service import DocumentProposalService
from web.backend.deps import (
    get_preferences,
    get_config, get_library_runtime_context, get_request_workspace,
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
    generation_mode: Literal["catalog", "standard", "deep"] = "standard"
    budget: dict[str, int] | None = None
    force_regenerate: bool = False


class WikiRunResumeRequest(BaseModel):
    provider: str | None = None
    additional_budget: dict[str, int] = Field(default_factory=dict)


class WikiPageCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    body: str = Field(..., min_length=1, max_length=60000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    related: list[str] = Field(default_factory=list, max_length=50)


class WikiPageUpdateRequest(WikiPageCreateRequest):
    expected_revision: int = Field(..., ge=1)


class WikiRepairDraftRequest(BaseModel):
    provider: str | None = None


def _service(request: Request) -> KBService:
    return KBService(get_request_workspace(request))


def _runtime_for(workspace: str):
    if workspace == get_workspace():
        return get_runtime_context()
    return get_library_runtime_context(workspace)


def _preferred_provider(requested: str | None, task: str | None = None) -> tuple[str | None, str | None]:
    """返回 (provider_name, model)。preference 存 `provider::model`（P5G.4）。"""
    from web.backend.deps import parse_provider_ref

    if requested:
        return parse_provider_ref(requested)
    config = get_config()
    preferences = get_preferences(config)
    if task:
        selected = preferences.get("ai", {}).get("task_providers", {}).get(task, "default")
        if selected and selected != "default":
            return parse_provider_ref(selected)
    return parse_provider_ref(preferences.get("ai", {}).get("default_provider"))


def _configure_wiki_provider(provider):
    if provider is not None:
        if hasattr(provider, "timeout"):
            provider.timeout = 120
        if hasattr(provider, "max_retries"):
            provider.max_retries = 2
    return provider


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


@router.post("/wiki/repair-plans")
def create_wiki_repair_plan(request: Request) -> dict:
    return unwrap_service_result(_service(request).maintain_wiki("plan"))


@router.get("/wiki/repair-plans/{plan_id}")
def get_wiki_repair_plan(plan_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).get_wiki_repair_plan(plan_id),
        status_code=404,
        code="wiki_repair_plan_not_found",
    )


@router.post("/wiki/repair-plans/{plan_id}/draft-ai")
def draft_wiki_repair_plan(plan_id: str, body: WikiRepairDraftRequest, request: Request) -> dict:
    workspace = get_request_workspace(request)
    try:
        provider = _configure_wiki_provider(_runtime_for(workspace).create_provider(*_preferred_provider(body.provider)))
    except ValueError as exc:
        raise APIError(409, "provider_unavailable", str(exc)) from exc
    return unwrap_service_result(
        _service(request).draft_wiki_repair_plan(plan_id, provider),
        status_code=409,
        code="wiki_repair_draft_failed",
    )


@router.post("/wiki/repair-plans/{plan_id}/apply")
def apply_wiki_repair_plan(plan_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).apply_wiki_repair_plan(plan_id, config=get_config()),
        status_code=409,
        code="wiki_repair_plan_not_applicable",
    )


@router.post("/wiki/pages")
def create_wiki_page(body: WikiPageCreateRequest, request: Request) -> dict:
    return unwrap_service_result(_service(request).create_wiki_page(
        title=body.title, body=body.body, tags=body.tags, related=body.related, config=get_config(),
    ), status_code=409, code="wiki_page_create_failed")


@router.get("/wiki/pages/{document_id}")
def get_wiki_page(document_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).get_wiki_page(document_id), status_code=404, code="wiki_page_not_found",
    )


@router.patch("/wiki/pages/{document_id}")
def update_wiki_page(document_id: str, body: WikiPageUpdateRequest, request: Request) -> dict:
    result = _service(request).update_wiki_page(
        document_id,
        expected_revision=body.expected_revision,
        title=body.title,
        body=body.body,
        tags=body.tags,
        related=body.related,
        config=get_config(),
    )
    return unwrap_service_result(result, status_code=409, code="wiki_page_revision_conflict")


@router.post("/wiki/pages/{document_id}/archive")
def archive_wiki_page(document_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).archive_wiki_page(document_id, config=get_config()),
        status_code=409,
        code="wiki_page_archive_failed",
    )


@router.post("/wiki/pages/{document_id}/restore")
def restore_wiki_page(document_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).restore_wiki_page(document_id, config=get_config()),
        status_code=409,
        code="wiki_page_restore_failed",
    )


@router.post("/wiki/maintenance/semantic")
def semantic_wiki_review(body: WikiSemanticReviewRequest, request: Request) -> dict:
    workspace = get_request_workspace(request)
    try:
        provider = _runtime_for(workspace).create_provider(*_preferred_provider(body.provider))
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
        provider = _runtime_for(workspace).create_provider(*_preferred_provider(body.provider))
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
            provider = _runtime_for(workspace).create_provider(*_preferred_provider(body.provider))
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
    provider = None
    discovery_provider = None
    try:
        if body.generation_mode != "catalog":
            provider = _configure_wiki_provider(_runtime_for(workspace).create_provider(*_preferred_provider(body.provider, "wiki_drafting")))
            discovery_provider = _configure_wiki_provider(_runtime_for(workspace).create_provider(*_preferred_provider(body.provider, "wiki_discovery")))
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
            generation_mode=body.generation_mode,
            budget=body.budget,
            force_regenerate=body.force_regenerate,
            discovery_provider=discovery_provider,
        ),
        status_code=409,
        code="wiki_run_failed",
    )


@router.post("/wiki/runs/estimate")
def estimate_wiki_run(body: WikiRunRequest, request: Request) -> dict:
    config = get_config()
    provider_name, _provider_model = _preferred_provider(body.provider, "wiki_drafting") or (None, None)
    provider_name = provider_name or ""
    provider_config = (config.get("llm", {}).get("providers") or {}).get(provider_name, {})
    return unwrap_service_result(_service(request).estimate_wiki_run(
        scope_mode=body.scope_mode,
        document_ids=body.document_ids,
        course=body.course,
        topic=body.topic,
        instruction=body.instruction,
        generation_mode=body.generation_mode,
        provider_name=provider_name,
        model=str(provider_config.get("model") or ""),
        config=config,
    ), status_code=409, code="wiki_run_estimate_failed")


@router.get("/wiki/runs/{run_id}")
def get_wiki_run(run_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).get_wiki_run(run_id),
        status_code=404,
        code="wiki_run_not_found",
    )


@router.post("/wiki/runs/{run_id}/resume")
def resume_wiki_run(run_id: str, body: WikiRunResumeRequest, request: Request) -> dict:
    workspace = get_request_workspace(request)
    try:
        provider = _configure_wiki_provider(_runtime_for(workspace).create_provider(*_preferred_provider(body.provider, "wiki_drafting")))
        discovery_provider = _configure_wiki_provider(_runtime_for(workspace).create_provider(*_preferred_provider(body.provider, "wiki_discovery")))
    except ValueError as exc:
        raise APIError(409, "provider_unavailable", str(exc)) from exc
    return unwrap_service_result(
        _service(request).resume_wiki_run(run_id, provider, body.additional_budget, discovery_provider),
        status_code=409,
        code="wiki_run_resume_failed",
    )


@router.post("/wiki/runs/{run_id}/cancel")
def cancel_wiki_run(run_id: str, request: Request) -> dict:
    return unwrap_service_result(
        _service(request).cancel_wiki_run(run_id), status_code=409, code="wiki_run_not_cancellable",
    )


@router.get("/wiki/runs/{run_id}/usage")
def wiki_run_usage(run_id: str, request: Request) -> dict:
    return unwrap_service_result(_service(request).wiki_run_usage(run_id))


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
            provider = _runtime_for(workspace).create_provider(*_preferred_provider(body.provider))
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


@router.get("/documents/{document_id}/extraction")
def document_extraction(document_id: str, request: Request) -> dict:
    result = _service(request).get_document_extraction(document_id)
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
    result = unwrap_service_result(
        _service(request).delete_document(document_id, config=get_config()),
        code="document_not_deletable",
    )
    result["sync"] = _public_sync(result["sync"])
    return result


class DocumentEditRequest(BaseModel):
    content: str
    expected_hash: str | None = None
    conflict_action: Literal["overwrite", "abandon", "save_as_new"] = "overwrite"


@router.get("/documents/{document_id}/content")
def document_content(document_id: str, request: Request) -> dict:
    return unwrap_service_result(
        DocumentEditService(get_request_workspace(request)).read(document_id),
        status_code=404,
        code="document_not_found",
    )


@router.put("/documents/{document_id}/content")
def edit_document(document_id: str, body: DocumentEditRequest, request: Request) -> dict:
    result = unwrap_service_result(
        DocumentEditService(get_request_workspace(request)).edit(
            document_id,
            body.content,
            expected_hash=body.expected_hash,
            conflict_action=body.conflict_action,
            config=get_config(),
        ),
        code="document_edit_failed",
    )
    if "sync" in result:
        result["sync"] = _public_sync(result["sync"])
    return result


@router.get("/documents/{document_id}/versions")
def document_versions(document_id: str, request: Request) -> dict:
    return unwrap_service_result(
        DocumentEditService(get_request_workspace(request)).list_versions(document_id),
        status_code=404,
        code="document_not_found",
    )


@router.post("/documents/{document_id}/versions/{version_id}/rollback")
def rollback_document(document_id: str, version_id: str, request: Request) -> dict:
    result = unwrap_service_result(
        DocumentEditService(get_request_workspace(request)).rollback(
            document_id, version_id, config=get_config()
        ),
        code="document_rollback_failed",
    )
    if "sync" in result:
        result["sync"] = _public_sync(result["sync"])
    return result


class DocumentProposalRequest(BaseModel):
    instruction: str
    provider: str | None = None


class NewDocumentProposalRequest(BaseModel):
    title: str
    content: str
    reason: str = ""


@router.post("/documents/{document_id}/proposals")
def create_document_proposal(document_id: str, body: DocumentProposalRequest, request: Request) -> dict:
    workspace = get_request_workspace(request)
    try:
        provider = _runtime_for(workspace).create_provider(*_preferred_provider(body.provider))
    except ValueError as exc:
        raise APIError(409, "provider_unavailable", str(exc)) from exc
    return unwrap_service_result(
        DocumentProposalService(workspace).create_proposal(document_id, body.instruction, provider),
        code="proposal_failed",
    )


@router.post("/proposals")
def create_new_document_proposal(body: NewDocumentProposalRequest, request: Request) -> dict:
    return unwrap_service_result(
        DocumentProposalService(get_request_workspace(request)).create_new_document_proposal(
            body.title, body.content, body.reason
        ),
        code="proposal_failed",
    )


@router.get("/proposals/{proposal_id}")
def get_document_proposal(proposal_id: str, request: Request) -> dict:
    return unwrap_service_result(
        DocumentProposalService(get_request_workspace(request)).get_proposal(proposal_id),
        status_code=404,
        code="proposal_not_found",
    )


@router.post("/proposals/{proposal_id}/apply")
def apply_document_proposal(proposal_id: str, request: Request) -> dict:
    return unwrap_service_result(
        DocumentProposalService(get_request_workspace(request)).apply_proposal(proposal_id, config=get_config()),
        code="proposal_apply_failed",
    )


@router.post("/proposals/{proposal_id}/undo")
def undo_document_proposal(proposal_id: str, request: Request) -> dict:
    return unwrap_service_result(
        DocumentProposalService(get_request_workspace(request)).undo_proposal(proposal_id, config=get_config()),
        code="proposal_undo_failed",
    )


class ConceptUpdateRequest(BaseModel):
    name: str | None = None
    definition: str | None = None
    aliases: list[str] | None = None
    note: str | None = None


class RelationshipCreateRequest(BaseModel):
    from_id: str
    to_id: str
    rel_type: str
    note: str = ""


@router.patch("/concepts/{concept_id}")
def update_concept(concept_id: str, body: ConceptUpdateRequest, request: Request) -> dict:
    if all(value is None for value in (body.name, body.definition, body.aliases, body.note)):
        raise APIError(400, "invalid_request", "At least one field is required.")
    return unwrap_service_result(
        ConceptService(get_request_workspace(request)).update_concept(
            concept_id,
            name=body.name,
            definition=body.definition,
            aliases=body.aliases,
            note=body.note,
        ),
        code="concept_update_failed",
    )


@router.post("/relationships")
def create_relationship(body: RelationshipCreateRequest, request: Request) -> dict:
    return unwrap_service_result(
        ConceptService(get_request_workspace(request)).create_relationship(
            from_id=body.from_id,
            to_id=body.to_id,
            rel_type=body.rel_type,
            note=body.note,
        ),
        code="relationship_create_failed",
    )


@router.delete("/relationships/{rel_id}")
def delete_relationship(rel_id: str, request: Request) -> dict:
    return unwrap_service_result(
        ConceptService(get_request_workspace(request)).delete_relationship(rel_id),
        code="relationship_delete_failed",
    )


@router.post("/search")
def search(body: KBSearchRequest, request: Request) -> dict:
    return unwrap_service_result(_service(request).search(
        query=body.query,
        course=body.course,
        top_k=body.top_k,
        mode=body.mode,
        config=get_config(),
    ))
