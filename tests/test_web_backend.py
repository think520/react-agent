"""Tests for the FastAPI backend skeleton."""

from __future__ import annotations

import os

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from web.backend.app import create_app
from web.backend.deps import reset_dependency_caches


@pytest.fixture
def backend_client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
llm:
  default_provider: dummy
  providers:
    dummy:
      type: deepseek
      api_key_env: DUMMY_API_KEY
      model: dummy-model
agent:
  timeout: 30
  max_retries: 0
session:
  save_dir: .session
  max_messages: 20
mcp:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOBODAN_CONFIG", str(config_path))
    monkeypatch.setenv("BOBODAN_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DUMMY_API_KEY", "test-key")
    reset_dependency_caches()
    try:
        yield TestClient(create_app())
    finally:
        reset_dependency_caches()


def test_health_endpoint(backend_client):
    response = backend_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_settings_endpoint_lists_providers(backend_client):
    response = backend_client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["default_provider"] == "dummy"
    assert data["providers"][0]["name"] == "dummy"
    assert data["providers"][0]["configured"] is True


def test_kb_status_returns_service_error_when_missing(backend_client):
    response = backend_client.get("/api/kb/status")
    assert response.status_code == 400
    assert "No knowledge base found" in response.json()["detail"]


def test_chat_run_streams_agent_events(backend_client, monkeypatch):
    class DummyProvider:
        def get_name(self):
            return "dummy"

    def fake_create_provider(config, provider_name):
        return {"ok": True, "provider": DummyProvider()}

    def fake_run_stream(**kwargs):
        yield {"type": "assistant_delta", "content": "Hi"}
        yield {"type": "assistant_done", "content": "Hi", "termination_reason": "final_answer"}

    monkeypatch.setattr("web.backend.routers.chat.AgentService.create_provider", fake_create_provider)
    monkeypatch.setattr("web.backend.routers.chat.AgentService.run_stream", fake_run_stream)

    response = backend_client.post("/api/chat/runs", json={"message": "hello", "save": False})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: run_start" in body
    assert "event: assistant_delta" in body
    assert '"content": "Hi"' in body
    assert "event: assistant_done" in body
    assert "event: run_end" in body
