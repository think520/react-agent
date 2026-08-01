"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .errors import APIError
from .routers import chat, graph, kb, learning, libraries, memory, quiz, research, settings
from .deps import get_config, get_library_service, get_session_save_dir, get_workspace


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        registry = get_library_service().list_libraries()
        if registry["libraries"]:
            for library in registry["libraries"]:
                try:
                    record = get_library_service().resolve(library["library_id"])
                    if record:
                        chat.migrate_unnamed_sessions(get_session_save_dir(get_config(), record["path"]))
                        from service.concept_service import ConceptService
                        ConceptService(record["path"]).recover_stale_runs()
                        from service.memory_consolidation import MemoryConsolidationService
                        MemoryConsolidationService(
                            record["path"],
                            config=get_config(),
                            session_dir=get_session_save_dir(get_config(), record["path"]),
                            legacy_workspace=get_workspace(),
                        ).resume_pending()
                except (OSError, ValueError):
                    continue
        else:
            chat.migrate_unnamed_sessions(get_session_save_dir(get_config()))
            from service.memory_consolidation import MemoryConsolidationService
            MemoryConsolidationService(
                get_workspace(),
                config=get_config(),
                session_dir=get_session_save_dir(get_config()),
                legacy_workspace=get_workspace(),
            ).resume_pending()
        yield

    app = FastAPI(title="Bobodan API", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def resolve_library(request: Request, call_next):
        scoped_prefixes = (
            "/api/chat", "/api/kb", "/api/quiz", "/api/learning",
            "/api/memory", "/api/settings/proposals", "/api/graph",
        )
        if request.url.path.startswith(scoped_prefixes):
            service = get_library_service()
            registry = service.list_libraries()
            library_id = request.headers.get("X-Bobodan-Library-ID")
            try:
                record = service.resolve(library_id) if registry["libraries"] else None
            except ValueError as exc:
                return JSONResponse(
                    status_code=409,
                    content={"error": {"code": "library_unavailable", "message": str(exc), "details": None}},
                )
            if registry["libraries"] and record is None:
                return JSONResponse(
                    status_code=409,
                    content={"error": {"code": "library_required", "message": "Select a Bobodan library first.", "details": None}},
                )
            request.state.library_id = record["library_id"] if record else None
            request.state.library_workspace = record["path"] if record else get_workspace()
        return await call_next(request)

    @app.exception_handler(APIError)
    async def api_error_handler(_request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request, exc: RequestValidationError
    ) -> JSONResponse:
        details = []
        for error in exc.errors():
            location = [str(part) for part in error.get("loc", ()) if part != "body"]
            details.append({
                "field": ".".join(location),
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "validation_error"),
            })
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed.",
                    "details": details,
                }
            },
        )

    app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(research.router, prefix="/api/chat/web", tags=["research"])
    app.include_router(kb.router, prefix="/api/kb", tags=["kb"])
    app.include_router(quiz.router, prefix="/api/quiz", tags=["quiz"])
    app.include_router(learning.router, prefix="/api/learning", tags=["learning"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(libraries.router, prefix="/api/libraries", tags=["libraries"])

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()
