"""Production static hosting for the React build (P5G.1).

`bobodan web` mounts the built frontend (`web/frontend/dist`) onto the same
FastAPI process that serves `/api/*`. Deep links like `/chat/...`,
`/library`, `/practice/...` fall back to `index.html` so the SPA router can
take over; `/api/*` is never intercepted.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

# web/backend/static.py → web → root → web/frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _spa_index(dist: Path) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">"
        "<title>Bobodan</title></head><body style=\"font-family: system-ui; "
        "padding: 40px; max-width: 560px; line-height: 1.7;\">"
        "<h1>前端尚未构建</h1>"
        "<p>当前运行的是纯 API 模式，浏览器页面还没有产物。</p>"
        "<p>请先构建前端，再重新启动：</p>"
        "<pre>cd web/frontend&#10;npm run build&#10;bobodan web</pre>"
        "</body></html>"
    )


def mount_frontend(app: FastAPI, dist_dir: Path | None = None) -> None:
    """Mount the SPA build. Safe to call once per app; no-op ordering with
    /api routes is guaranteed because catch-all is registered last."""
    dist = Path(dist_dir) if dist_dir else FRONTEND_DIST
    dist = dist.resolve()

    @app.get("/", include_in_schema=False, response_model=None)
    def index() -> FileResponse | HTMLResponse:
        index_file = dist / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return _spa_index(dist)

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    def spa_fallback(full_path: str) -> FileResponse | HTMLResponse:
        # Never swallow API routes (explicit /api/* routes are registered
        # earlier and match first; this is the defensive backstop).
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index_file = dist / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return _spa_index(dist)
