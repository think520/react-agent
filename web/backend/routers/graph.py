"""Graph / knowledge-map endpoints — P5E.6."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from service.concept_service import ConceptService
from web.backend.deps import get_config, get_default_provider_name, get_request_workspace
from web.backend.errors import APIError, unwrap_service_result

router = APIRouter()


def _svc(request: Request) -> ConceptService:
    return ConceptService(get_request_workspace(request))


def _unwrap(result: dict) -> dict:
    return unwrap_service_result(result)


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


class SavePositionsRequest(BaseModel):
    positions: list[dict] = Field(..., max_length=500)
    view_id: str = Field(default="default", max_length=64)


class ExtractRequest(BaseModel):
    document_id: str = Field(..., min_length=1)
    document_title: str = Field(default="", max_length=300)
    document_path: str = Field(default="", max_length=500)
    content: str = Field(..., min_length=1, max_length=40000)
    provider: str | None = None


# ------------------------------------------------------------------
# Graph state
# ------------------------------------------------------------------

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
) -> dict:
    return _unwrap(_svc(request).list_candidates(status=status))


@router.post("/candidates/{candidate_id}/action")
def candidate_action(
    candidate_id: str,
    body: CandidateActionRequest,
    request: Request,
) -> dict:
    svc = _svc(request)
    if body.action == "confirm":
        return _unwrap(svc.confirm_candidate(candidate_id))
    if body.action == "reject":
        return _unwrap(svc.reject_candidate(candidate_id, suppress_days=body.suppress_days))
    if body.action == "label":
        return _unwrap(svc.demote_candidate_to_label(candidate_id))
    raise APIError(400, "invalid_action", f"Unknown action: {body.action}")


# ------------------------------------------------------------------
# Extraction
# ------------------------------------------------------------------

@router.post("/extract")
def extract_concepts(body: ExtractRequest, request: Request) -> dict:
    from providers.factory import ProviderFactory
    config = get_config()
    provider_name = body.provider or get_default_provider_name(config)
    try:
        llm = ProviderFactory.create(config, provider_name)
    except Exception as exc:
        raise APIError(503, "provider_unavailable", str(exc)) from exc
    return _unwrap(_svc(request).extract_from_document(
        document_id=body.document_id,
        document_title=body.document_title,
        document_path=body.document_path,
        content=body.content,
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
