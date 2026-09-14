"""P5G.1: production static hosting and SPA deep-link fallback."""

import sys

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from web.backend.app import create_app
from web.backend.static import mount_frontend


@pytest.fixture
def dist_dir(tmp_path):
    """A fake frontend build with index.html and one asset."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><head><title>Bobodan</title></head>"
        '<body><div id="root"></div><script src="/assets/app.js"></script></body></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('app');", encoding="utf-8")
    return dist


@pytest.fixture
def client(dist_dir):
    app = create_app()
    mount_frontend(app, dist_dir)
    return TestClient(app)


def test_root_serves_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="root"' in response.text


def test_deep_link_falls_back_to_index(client):
    for path in ("/library", "/practice", "/chat/abc-123", "/knowledge-map"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="root"' in response.text, path


def test_asset_served_with_correct_type(client):
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/javascript"
    assert response.text == "console.log('app');"


def test_api_routes_are_not_swallowed(client):
    response = client.get("/api/nonexistent-route")
    assert response.status_code == 404


def test_health_still_works(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_missing_dist_shows_build_hint(tmp_path):
    app = create_app()
    mount_frontend(app, tmp_path / "no-such-dist")
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "前端尚未构建" in response.text

_CANARY = "TOP-SECRET-TRAVERSAL-CANARY"


def _write_canary(tmp_path):
    """A file sitting next to dist — the parent of dist is not public."""
    secret = tmp_path / "secret.txt"
    secret.write_text(_CANARY, encoding="utf-8")
    return secret


def test_percent_encoded_traversal_cannot_escape_dist(client, tmp_path):
    """P0-4: `dist/../secret.txt` must never be served.

    Before the fix `candidate = dist / full_path` resolved outside the build
    directory and FileResponse happily returned the file.
    """
    _write_canary(tmp_path)
    for path in (
        "/..%2Fsecret.txt",
        "/..%2fsecret.txt",
        "/%2e%2e%2fsecret.txt",
        "/assets/..%2F..%2Fsecret.txt",
    ):
        response = client.get(path)
        assert response.status_code == 404, path
        assert _CANARY not in response.text, path


@pytest.mark.skipif(sys.platform != "win32", reason="drive-absolute paths are Windows-specific")
def test_absolute_path_cannot_escape_dist(client, tmp_path):
    """P0-4: on Windows `dist / "C:/..."` replaces the base entirely."""
    secret = _write_canary(tmp_path)
    response = client.get("/" + secret.as_posix())
    assert response.status_code == 404
    assert _CANARY not in response.text

