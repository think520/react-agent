"""Memory endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from service.memory_service import MemoryService
from web.backend.deps import get_workspace

router = APIRouter()


class SaveMemoryRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    content: str = Field(..., min_length=1)
    entry_type: str = "user"


class DailySaveRequest(BaseModel):
    content: str = Field(..., min_length=1)
    tags: list[str] | None = None


def _service() -> MemoryService:
    return MemoryService(get_workspace())


def _unwrap(result: dict):
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "request failed"))
    return result


@router.get("")
def list_entries() -> dict:
    return _unwrap(_service().list_entries())


@router.post("")
def save_memory(request: SaveMemoryRequest) -> dict:
    return _unwrap(_service().save(
        name=request.name,
        description=request.description,
        content=request.content,
        entry_type=request.entry_type,
    ))


@router.get("/search")
def recall(query: str, top_k: int = 5) -> dict:
    return _unwrap(_service().recall(query=query, top_k=top_k))


@router.get("/stats")
def stats() -> dict:
    return _unwrap(_service().get_stats())


@router.post("/daily")
def daily_save(request: DailySaveRequest) -> dict:
    return _unwrap(_service().daily_save(request.content, tags=request.tags))


@router.get("/daily/read")
def daily_read(date: str | None = None) -> dict:
    return _unwrap(_service().daily_read(date=date))


@router.post("/promote")
def promote(dry_run: bool = False) -> dict:
    return _unwrap(_service().promote(dry_run=dry_run))


@router.get("/{name}")
def get_entry(name: str) -> dict:
    return _unwrap(_service().get_entry(name))


@router.delete("/{name}")
def forget(name: str) -> dict:
    return _unwrap(_service().forget(name))
