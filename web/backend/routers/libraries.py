"""Registered portable library endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from web.backend.deps import get_config, get_library_service
from web.backend.errors import APIError


router = APIRouter()


class CreateLibraryRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    parent_path: str = Field(..., min_length=1)


class OpenLibraryRequest(BaseModel):
    path: str = Field(..., min_length=1)


class MigrateLibraryRequest(BaseModel):
    path: str = Field(..., min_length=1)
    name: str | None = Field(default=None, max_length=120)


def _bad_request(exc: ValueError) -> APIError:
    return APIError(409, "library_unavailable", str(exc))


@router.get("")
def list_libraries() -> dict:
    return get_library_service().list_libraries()


@router.post("")
def create_library(request: CreateLibraryRequest) -> dict:
    try:
        return get_library_service().create(request.name, request.parent_path)
    except (OSError, ValueError) as exc:
        raise _bad_request(ValueError(str(exc))) from exc


@router.post("/open")
def open_library(request: OpenLibraryRequest) -> dict:
    try:
        return get_library_service().register(request.path, activate=True)
    except (OSError, ValueError) as exc:
        raise _bad_request(ValueError(str(exc))) from exc


@router.post("/migrate/preview")
def preview_library_migration(request: OpenLibraryRequest) -> dict:
    try:
        return get_library_service().preview_migration(request.path)
    except (OSError, ValueError) as exc:
        raise _bad_request(ValueError(str(exc))) from exc


@router.post("/migrate")
def migrate_library(request: MigrateLibraryRequest) -> dict:
    try:
        return get_library_service().migrate(request.path, name=request.name, config=get_config())
    except (OSError, ValueError) as exc:
        raise _bad_request(ValueError(str(exc))) from exc


@router.post("/{library_id}/activate")
def activate_library(library_id: str) -> dict:
    try:
        return get_library_service().activate(library_id)
    except (OSError, ValueError) as exc:
        raise APIError(404, "library_not_found", str(exc)) from exc


@router.post("/{library_id}/sync")
def sync_library(library_id: str) -> dict:
    try:
        return get_library_service().sync(library_id, get_config())
    except (OSError, ValueError) as exc:
        raise _bad_request(ValueError(str(exc))) from exc


@router.delete("/{library_id}")
def unregister_library(library_id: str) -> dict:
    if not get_library_service().unregister(library_id):
        raise APIError(404, "library_not_found", "Library not found")
    return {"unregistered": True, "library_id": library_id}
