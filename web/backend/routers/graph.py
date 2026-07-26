"""Graph / knowledge-map endpoints — P5E.6."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, Field

from service.concept_service import ConceptService
from web.backend.deps import get_config, get_default_provider_name, get_request_workspace
from web.backend.errors import APIError, unwrap_service_result

router = APIRouter()


def _svc(request: Request) -> ConceptService:
    return ConceptService(get_request_workspace(request))


def _unwrap(result: dict) -> dict:
    return unwrap_service_result(result)


def _create_llm_provider(config: dict, provider_name: str):
    from providers.factory import ProviderFactory

    extraction_config = config.get("concept_extraction") or {}
    providers = config.get("llm", {}).get("providers") or {}
    provider_config = providers.get(provider_name)
    if not isinstance(provider_config, dict):
        raise APIError(
            503,
            "provider_unavailable",
            f"Provider '{provider_name}' is not configured.",
        )
    try:
        effective_provider = dict(provider_config)
        if extraction_config.get("model"):
            effective_provider["model"] = extraction_config["model"]
        effective_agent = dict(config.get("agent", {}))
        effective_agent["temperature"] = float(extraction_config.get("temperature", 0.2))
        if extraction_config.get("timeout") is not None:
            effective_agent["timeout"] = extraction_config["timeout"]
        if extraction_config.get("max_retries") is not None:
            effective_agent["max_retries"] = extraction_config["max_retries"]
        return ProviderFactory.create(effective_provider, effective_agent)
    except Exception as exc:
        raise APIError(503, "provider_unavailable", str(exc)) from exc


# ------------------------------------------------------------------
# Request bodies
# ------------------------------------------------------------------

class ConceptUpsertRequest(BaseModel):
    concept_id: str | None = None
    name: str = Field(..., min_length=1, max_length=120)
    level: Literal["cluster", "core", "detail"] = "core"
    definition: str = Field(default="", max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    topic_ids: list[str] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=2000)


class RelationshipRequest(BaseModel):
    from_id: str = Field(..., min_length=1)
    to_id: str = Field(..., min_length=1)
    rel_type: str = Field(..., min_length=1)
    evidence_level: Literal["source", "cross", "user", "ai"] = "user"
    note: str = Field(default="", max_length=1000)


class CandidateActionRequest(BaseModel):
    action: Literal["confirm", "reject", "label"]
    suppress_days: int = Field(default=14, ge=0, le=365)
    relation_edits: list[dict] = Field(default_factory=list, max_length=100)


class CandidateBatchConfirmRequest(BaseModel):
    candidate_ids: list[str] = Field(..., min_length=1, max_length=100)
    relation_edits: list[dict] = Field(default_factory=list, max_length=500)


class SavePositionsRequest(BaseModel):
    positions: list[dict] = Field(..., max_length=500)
    view_id: str = Field(default="default", max_length=64)


class ExtractRequest(BaseModel):
    document_id: str = Field(..., min_length=1)
    document_title: str = Field(default="", max_length=300)
    document_path: str = Field(default="", max_length=500)
    content: str = Field(..., min_length=1, max_length=40000)
    sections: list[dict] = Field(default_factory=list, max_length=200)
    content_version: str = Field(default="", max_length=200)
    provider: str | None = None
    force: bool = False


class LegacyGraphImportRequest(BaseModel):
    concept_ids: list[str] = Field(default_factory=list, max_length=1000)
    memory_ids: list[str] = Field(default_factory=list, max_length=1000)
    archive: bool = True


# ------------------------------------------------------------------
# Graph state
# ------------------------------------------------------------------

@router.get("/legacy/preview")
def legacy_graph_preview(request: Request) -> dict:
    from service.legacy_graph_migration import LegacyGraphMigrationService

    return _unwrap(LegacyGraphMigrationService(get_request_workspace(request)).preview())


@router.post("/legacy/import")
def legacy_graph_import(body: LegacyGraphImportRequest, request: Request) -> dict:
    from service.legacy_graph_migration import LegacyGraphMigrationService

    return _unwrap(LegacyGraphMigrationService(get_request_workspace(request)).migrate(
        concept_ids=body.concept_ids,
        memory_ids=body.memory_ids,
        archive=body.archive,
    ))

@router.get("/state")
def graph_state(
    request: Request,
    topic_id: str | None = None,
    include_candidates: bool = False,
    view_id: str = "default",
) -> dict:
    return _unwrap(_svc(request).get_graph_state(
        topic_id=topic_id,
        include_candidates=include_candidates,
        view_id=view_id,
    ))


@router.get("/subgraph/{concept_id}")
def subgraph(
    concept_id: str,
    request: Request,
    view_id: str = "default",
) -> dict:
    return _unwrap(_svc(request).get_subgraph(concept_id, view_id=view_id))


# ------------------------------------------------------------------
# Concepts
# ------------------------------------------------------------------

@router.get("/concepts/{concept_id}")
def get_concept(concept_id: str, request: Request) -> dict:
    return _unwrap(_svc(request).get_concept(concept_id))


@router.post("/concepts")
def upsert_concept(body: ConceptUpsertRequest, request: Request) -> dict:
    return _unwrap(_svc(request).upsert_concept(
        concept_id=body.concept_id,
        name=body.name,
        level=body.level,
        definition=body.definition,
        aliases=body.aliases,
        topic_ids=body.topic_ids,
        note=body.note,
    ))


@router.patch("/concepts/{concept_id}")
def patch_concept(
    concept_id: str,
    body: ConceptUpsertRequest,
    request: Request,
) -> dict:
    return _unwrap(_svc(request).upsert_concept(
        concept_id=concept_id,
        name=body.name,
        level=body.level,
        definition=body.definition,
        aliases=body.aliases,
        topic_ids=body.topic_ids,
        note=body.note,
    ))


@router.delete("/concepts/{concept_id}")
def delete_concept(concept_id: str, request: Request) -> dict:
    return _unwrap(_svc(request).delete_concept(concept_id))


# ------------------------------------------------------------------
# Relationships
# ------------------------------------------------------------------

@router.post("/relationships")
def add_relationship(body: RelationshipRequest, request: Request) -> dict:
    return _unwrap(_svc(request).add_relationship(
        from_id=body.from_id,
        to_id=body.to_id,
        rel_type=body.rel_type,
        evidence_level=body.evidence_level,
        note=body.note,
    ))


@router.delete("/relationships/{rel_id}")
def delete_relationship(rel_id: str, request: Request) -> dict:
    return _unwrap(_svc(request).delete_relationship(rel_id))


# ------------------------------------------------------------------
# Candidates
# ------------------------------------------------------------------

@router.get("/candidates")
def list_candidates(
    request: Request,
    status: str = "pending",
    document_id: str | None = None,
) -> dict:
    return _unwrap(_svc(request).list_candidates(
        status=status,
        source_doc_id=document_id,
    ))


@router.post("/candidates/{candidate_id}/action")
def candidate_action(
    candidate_id: str,
    body: CandidateActionRequest,
    request: Request,
) -> dict:
    svc = _svc(request)
    if body.action == "confirm":
        return _unwrap(svc.confirm_candidate(candidate_id, relation_edits=body.relation_edits))
    if body.action == "reject":
        return _unwrap(svc.reject_candidate(candidate_id, suppress_days=body.suppress_days))
    if body.action == "label":
        return _unwrap(svc.demote_candidate_to_label(candidate_id))
    raise APIError(400, "invalid_action", f"Unknown action: {body.action}")


@router.post("/candidates/confirm")
def confirm_candidates(body: CandidateBatchConfirmRequest, request: Request) -> dict:
    return _unwrap(_svc(request).confirm_candidates(
        body.candidate_ids,
        relation_edits=body.relation_edits,
    ))


# ------------------------------------------------------------------
# Extraction
# ------------------------------------------------------------------

@router.post("/extractions", status_code=202)
def start_extraction(
    body: ExtractRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    svc = _svc(request)
    created = _unwrap(svc.create_extraction_run(
        document_id=body.document_id,
        document_title=body.document_title,
        content_version=body.content_version,
        force=body.force,
    ))
    run = created["run"]
    if created["started"]:
        config = get_config()
        extraction_config = config.get("concept_extraction") or {}
        provider_name = body.provider or extraction_config.get("provider") or get_default_provider_name(config)
        try:
            llm = _create_llm_provider(config, provider_name)
        except APIError as exc:
            svc.fail_extraction_run(run["run_id"], exc.message)
            raise
        background_tasks.add_task(
            svc.execute_extraction_run,
            run_id=run["run_id"],
            document_id=body.document_id,
            document_title=body.document_title,
            document_path=body.document_path,
            content=body.content,
            sections=body.sections,
            llm_provider=llm,
        )
    return {"run": run, "started": created["started"]}


@router.get("/extractions")
def extraction_statuses(request: Request) -> dict:
    return _unwrap(_svc(request).list_extraction_statuses())


@router.get("/extractions/{run_id}")
def extraction_status(run_id: str, request: Request) -> dict:
    return _unwrap(_svc(request).get_extraction_run(run_id))


@router.post("/extractions/{run_id}/retry", status_code=202)
def retry_failed_sections(
    run_id: str,
    body: ExtractRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    svc = _svc(request)
    previous = _unwrap(svc.get_extraction_run(run_id))["run"]
    if previous["document_id"] != body.document_id:
        raise APIError(409, "extraction_document_mismatch", "The retry request does not match the original document.")
    failed_sections = previous.get("failed_sections") or []
    if not failed_sections:
        raise APIError(409, "no_failed_sections", "This extraction has no failed sections to retry.")
    failed_chunk_ids = {str(item.get("chunk_id")) for item in failed_sections if item.get("chunk_id")}
    failed_indexes = {int(item["index"]) for item in failed_sections if item.get("index") is not None}
    retry_sections = [
        section for index, section in enumerate(body.sections)
        if str(section.get("chunk_id") or section.get("id") or "") in failed_chunk_ids or index in failed_indexes
    ]
    if not retry_sections:
        raise APIError(409, "failed_sections_missing", "The failed sections are no longer present in this document version.")
    created = _unwrap(svc.create_extraction_run(
        document_id=body.document_id,
        document_title=body.document_title,
        content_version=body.content_version,
        force=True,
    ))
    config = get_config()
    extraction_config = config.get("concept_extraction") or {}
    provider_name = body.provider or extraction_config.get("provider") or get_default_provider_name(config)
    try:
        llm = _create_llm_provider(config, provider_name)
    except APIError as exc:
        svc.fail_extraction_run(created["run"]["run_id"], exc.message)
        raise
    background_tasks.add_task(
        svc.execute_extraction_run,
        run_id=created["run"]["run_id"],
        document_id=body.document_id,
        document_title=body.document_title,
        document_path=body.document_path,
        content=body.content,
        sections=retry_sections,
        llm_provider=llm,
        incremental=True,
    )
    return {"run": created["run"], "started": True, "retried_sections": len(retry_sections)}

@router.post("/extract")
def extract_concepts(body: ExtractRequest, request: Request) -> dict:
    config = get_config()
    extraction_config = config.get("concept_extraction") or {}
    provider_name = body.provider or extraction_config.get("provider") or get_default_provider_name(config)
    llm = _create_llm_provider(config, provider_name)
    return _unwrap(_svc(request).extract_from_document(
        document_id=body.document_id,
        document_title=body.document_title,
        document_path=body.document_path,
        content=body.content,
        sections=body.sections,
        llm_provider=llm,
    ))


# ------------------------------------------------------------------
# Positions
# ------------------------------------------------------------------

@router.post("/positions")
def save_positions(body: SavePositionsRequest, request: Request) -> dict:
    return _unwrap(_svc(request).save_positions(
        body.positions,
        view_id=body.view_id,
    ))
