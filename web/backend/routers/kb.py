"""Knowledge base and managed library endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel, Field

from service.kb_service import KBService
from web.backend.deps import get_config, get_workspace
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


def _service() -> KBService:
    return KBService(get_workspace())


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
def status() -> dict:
    result = _service().status()
    if not result.get("ok"):
        raise APIError(404, "knowledge_base_not_found", result["error"])
    return result


@router.post("/sync")
def sync(request: KBSyncRequest) -> dict:
    result = unwrap_service_result(_service().sync(
        vault_path=request.vault_path,
        course_dir=request.course_dir,
        mode=request.mode,
        config=get_config(),
    ))
    return _public_sync(result)


@router.post("/import")
async def import_files(files: list[UploadFile] = File(...)) -> dict:
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
    result = unwrap_service_result(_service().import_files(payload, config=get_config()))
    result["sync"] = _public_sync(result["sync"])
    return result


@router.get("/documents")
def documents(course: str | None = None) -> dict:
    return unwrap_service_result(_service().list_documents(course=course))


@router.get("/documents/{document_id}")
def document_detail(document_id: str) -> dict:
    result = _service().get_document(document_id)
    if not result.get("ok"):
        raise APIError(404, "document_not_found", result["error"])
    return result


@router.post("/search")
def search(request: KBSearchRequest) -> dict:
    return unwrap_service_result(_service().search(
        query=request.query,
        course=request.course,
        top_k=request.top_k,
        mode=request.mode,
        config=get_config(),
    ))


@router.post("/graph")
def graph_query(request: GraphQueryRequest) -> dict:
    return unwrap_service_result(_service().graph_query(
        concept=request.concept,
        intent=request.intent,
        limit=request.limit,
    ))
