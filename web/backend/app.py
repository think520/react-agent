"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from .routers import chat, kb, learning, memory, quiz, settings


def create_app() -> FastAPI:
    app = FastAPI(title="Bobodan API", version="0.1.0")
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
