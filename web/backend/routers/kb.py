"""Knowledge base endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from service.kb_service import KBService
from web.backend.deps import get_config, get_workspace

router = APIRouter()


class KBSyncRequest(BaseModel):
    vault_path: str
    course_dir: str | None = None
    mode: str = "incremental"


class KBSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    course: str | None = None
    top_k: int = 5
    mode: str = "auto"


class GraphQueryRequest(BaseModel):
    concept: str = Field(..., min_length=1)
    intent: str = "related"
    limit: int = 20


def _service() -> KBService:
    return KBService(get_workspace())


def _unwrap(result: dict):
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "request failed"))
    return result


@router.get("/status")
def status() -> dict:
    return _unwrap(_service().status())


@router.post("/sync")
def sync(request: KBSyncRequest) -> dict:
    return _unwrap(_service().sync(
        vault_path=request.vault_path,
        course_dir=request.course_dir,
        mode=request.mode,
        config=get_config(),
    ))


@router.post("/search")
def search(request: KBSearchRequest) -> dict:
    return _unwrap(_service().search(
        query=request.query,
        course=request.course,
        top_k=request.top_k,
        mode=request.mode,
        config=get_config(),
    ))


@router.post("/graph")
def graph_query(request: GraphQueryRequest) -> dict:
    return _unwrap(_service().graph_query(
        concept=request.concept,
        intent=request.intent,
        limit=request.limit,
    ))
