"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .errors import APIError
from .routers import chat, kb, learning, memory, quiz, settings


def create_app() -> FastAPI:
    app = FastAPI(title="Bobodan API", version="0.1.0")

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

    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(kb.router, prefix="/api/kb", tags=["kb"])
    app.include_router(quiz.router, prefix="/api/quiz", tags=["quiz"])
    app.include_router(learning.router, prefix="/api/learning", tags=["learning"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()
