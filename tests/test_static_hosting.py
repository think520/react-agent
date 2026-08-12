"""P5G.1: production static hosting and SPA deep-link fallback."""

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
