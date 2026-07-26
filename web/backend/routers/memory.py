"""Memory endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from service.memory_service import MemoryService
from web.backend.deps import (
    get_preferences,
    get_config, get_request_workspace, get_workspace,
)
from web.backend.errors import APIError, unwrap_service_result

router = APIRouter()


class KnowledgeCreateRequest(BaseModel):
    scope: str
    kind: str
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1, max_length=5000)
    pinned: bool = False
    evidence: list[dict] = Field(default_factory=list, max_length=50)


class KnowledgeUpdateRequest(BaseModel):
    revision: int = Field(..., ge=1)
    patch: dict


class CandidateResolutionRequest(BaseModel):
    edits: dict = Field(default_factory=dict)


class ReadingProgressRequest(BaseModel):
    progress: int = Field(default=0, ge=0, le=100)
    opened: bool = False


class LegacyImportRequest(BaseModel):
    selections: list[dict[str, str]] = Field(default_factory=list, max_length=200)


class ConsolidateRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)


def _service(request: Request) -> MemoryService:
    return MemoryService(get_request_workspace(request), legacy_workspace=get_workspace())


def _unwrap(result: dict):
    return unwrap_service_result(result)


def _require_memory_write_enabled() -> None:
    config = get_config()
    preferences = get_preferences(config)
    if not (
        config.get("memory", {}).get("enabled", True)
        and preferences.get("memory", {}).get("enabled", True)
    ):
        raise APIError(409, "memory_disabled", "Learning memory is disabled. Enable it before saving personal knowledge.")


@router.get("/overview")
def overview(request: Request) -> dict:
    return _unwrap(_service(request).overview())


@router.get("/knowledge")
def list_knowledge(request: Request, scope: str = "all", query: str = "", kind: str | None = None, limit: int = 100) -> dict:
    return _unwrap(_service(request).list_knowledge(scope=scope, query=query, kind=kind, limit=limit))


@router.post("/knowledge")
def create_knowledge(body: KnowledgeCreateRequest, request: Request) -> dict:
    _require_memory_write_enabled()
    return _unwrap(_service(request).create_knowledge(**body.model_dump()))


@router.patch("/knowledge/{item_id}")
def update_knowledge(item_id: str, body: KnowledgeUpdateRequest, request: Request) -> dict:
    _require_memory_write_enabled()
    return _unwrap(_service(request).update_knowledge(item_id, body.revision, body.patch))


@router.delete("/knowledge/{item_id}")
def delete_knowledge(item_id: str, request: Request) -> dict:
    return _unwrap(_service(request).delete_knowledge(item_id))


@router.get("/candidates")
def list_candidates(request: Request, status: str = "pending", scope: str = "all", limit: int = 100) -> dict:
    return _unwrap(_service(request).list_candidates(status=status, scope=scope, limit=limit))


@router.post("/candidates/{candidate_id}/confirm")
def confirm_candidate(candidate_id: str, body: CandidateResolutionRequest, request: Request) -> dict:
    _require_memory_write_enabled()
    return _unwrap(_service(request).confirm_candidate(candidate_id, body.edits))


@router.post("/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, request: Request) -> dict:
    return _unwrap(_service(request).reject_candidate(candidate_id))


@router.get("/events")
def list_events(request: Request, limit: int = 100, event_type: str | None = None) -> dict:
    return _unwrap(_service(request).list_events(limit=limit, event_type=event_type))


@router.put("/reading-progress/{document_id}")
def reading_progress(document_id: str, body: ReadingProgressRequest, request: Request) -> dict:
    return _unwrap(_service(request).update_reading_progress(document_id, body.progress, opened=body.opened))


@router.get("/legacy/preview")
def legacy_preview(request: Request) -> dict:
    return _unwrap(_service(request).legacy_preview())


@router.post("/legacy/import")
def legacy_import(body: LegacyImportRequest, request: Request) -> dict:
    _require_memory_write_enabled()
    return _unwrap(_service(request).import_legacy(body.selections))


@router.get("/export", response_class=PlainTextResponse)
def export_knowledge(request: Request, scope: str = "all") -> PlainTextResponse:
    result = _unwrap(_service(request).export_knowledge(scope=scope))
    return PlainTextResponse(
        result["content"],
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bobodan-personal-knowledge.md"'},
    )


@router.post("/consolidate")
def consolidate(body: ConsolidateRequest, request: Request) -> dict:
    from service.memory_consolidation import MemoryConsolidationService
    _require_memory_write_enabled()
    return _unwrap(MemoryConsolidationService(
        get_request_workspace(request), legacy_workspace=get_workspace(),
    ).consolidate_now(session_id=body.session_id))
