"""Contract tests for the FastAPI backend used by the future Web UI."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from core.session import Session
from web.backend.app import create_app
from web.backend.deps import reset_dependency_caches
from web.backend.routers.chat import _slash_command_prompt


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
        client = TestClient(create_app())
        client.workspace = tmp_path
        yield client
    finally:
        reset_dependency_caches()


def test_health_endpoint(backend_client):
    response = backend_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_settings_endpoint_lists_providers_without_absolute_workspace(backend_client):
    response = backend_client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["default_provider"] == "dummy"
    assert data["providers"][0]["name"] == "dummy"
    assert data["providers"][0]["configured"] is True
    assert data["workspace_name"] == backend_client.workspace.name
    assert data["skills"] == []
    assert str(backend_client.workspace) not in response.text


def test_settings_endpoint_lists_local_skills(backend_client):
    skill_dir = backend_client.workspace / "skills" / "study-loop"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: study-loop\ndescription: 帮助整理学习任务。\n---\n\n# Study Loop",
        encoding="utf-8",
    )

    response = backend_client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["skills"] == [{
        "name": "study-loop",
        "description": "帮助整理学习任务。",
    }]
    assert "SKILL.md" not in response.text


def test_web_backend_loads_provider_key_from_workspace_dotenv(backend_client, monkeypatch):
    monkeypatch.delenv("DUMMY_API_KEY", raising=False)
    (backend_client.workspace / ".env").write_text(
        "DUMMY_API_KEY=dotenv-test-key\n",
        encoding="utf-8",
    )
    reset_dependency_caches()

    response = backend_client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["providers"][0]["configured"] is True


def test_kb_status_returns_structured_not_found(backend_client):
    response = backend_client.get("/api/kb/status")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "knowledge_base_not_found"
    assert "No knowledge base found" in response.json()["error"]["message"]


def test_wiki_maintenance_contract(backend_client, monkeypatch):
    monkeypatch.setattr(
        "web.backend.routers.kb.KBService.wiki_health",
        lambda self: {"ok": True, "healthy": True, "total_pages": 6, "vaults": []},
    )
    monkeypatch.setattr(
        "web.backend.routers.kb.KBService.maintain_wiki",
        lambda self, action: {
            "ok": True,
            "archived_count": 2,
            "canonical_count": 6,
            "health": {"healthy": True, "total_pages": 6, "vaults": []},
        },
    )

    status = backend_client.get("/api/kb/wiki/maintenance")
    maintained = backend_client.post("/api/kb/wiki/maintenance", json={"action": "organize"})

    assert status.status_code == 200
    assert status.json()["total_pages"] == 6
    assert maintained.status_code == 200
    assert maintained.json()["archived_count"] == 2


def test_explicit_skill_slash_command_loads_selected_skill(tmp_path):
    skill_dir = tmp_path / "skills" / "exam-prep"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: exam-prep\ndescription: 复习。\n---\n\n只围绕薄弱点出题。",
        encoding="utf-8",
    )

    prompt = _slash_command_prompt("/skill exam-prep 复习 RAG", str(tmp_path / "skills"))

    assert prompt is not None
    assert "exam-prep" in prompt
    assert "复习 RAG" in prompt
    assert "只围绕薄弱点出题" in prompt


def test_validation_errors_use_stable_error_contract(backend_client):
    response = backend_client.post("/api/chat/runs", json={"message": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["details"][0]["field"] == "message"


def test_chat_run_maps_safe_events_and_injects_runtime(backend_client, monkeypatch):
    captured = {}

    class DummyProvider:
        def get_name(self):
            return "dummy"

    runtime = SimpleNamespace(
        workspace=str(backend_client.workspace),
        skills_prompt="skills prompt",
        memory_prompt="memory prompt",
        create_provider=lambda _name: DummyProvider(),
        refresh_memory=lambda: "memory prompt",
        create_trace=lambda _session_id: object(),
    )

    def fake_run_stream(**kwargs):
        captured.update(kwargs)
        yield {"type": "tool_start", "tool_name": "rag_search"}
        yield {
            "type": "tool_end",
            "tool_name": "rag_search",
            "ok": True,
            "content": "SECRET raw tool output C:\\private\\notes.md",
            "artifacts": [{
                "type": "citation",
                "attribution": {
                    "kind": "local",
                    "sources": [{
                        "source_type": "local",
                        "source_id": "chunk-1",
                        "title": "Lesson 1",
                    }],
                },
            }],
        }
        yield {"type": "assistant_delta", "content": "Hi"}
        yield {"type": "assistant_done", "content": "Hi", "termination_reason": "final_answer"}

    monkeypatch.setattr("web.backend.routers.chat.get_runtime_context", lambda: runtime)
    monkeypatch.setattr("web.backend.routers.chat.AgentService.run_stream", fake_run_stream)
    monkeypatch.setattr(
        "web.backend.routers.chat.KBService.list_documents",
        lambda self, collection: {"ok": True, "documents": [{
            "document_id": "doc-1", "title": "Lesson 1", "source": "course/lesson.md",
        }]},
    )

    response = backend_client.post("/api/chat/runs", json={
        "message": "hello", "document_ids": ["doc-1"], "save": False,
    })
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: run_started" in body
    assert "event: status" in body
    assert "event: citation" in body
    assert "event: message_delta" in body
    assert "event: run_completed" in body
    assert '"content": "Hi"' in body
    assert "SECRET" not in body
    assert "C:\\private" not in body
    assert captured["skills_prompt"] == "skills prompt"
    assert captured["memory_prompt"] == "memory prompt"
    assert captured["trace_writer"] is not None
    assert "Lesson 1" in captured["request_prompt"]
    assert captured["session"].active_document_ids == ["doc-1"]
    assert "rag_search" in captured["allowed_tool_names"]
    assert "write_file" not in captured["allowed_tool_names"]
    schema_names = {
        item["function"]["name"] for item in captured["tools_schema"]
    }
    assert schema_names == set(captured["allowed_tool_names"])


def test_chat_stream_error_does_not_leak_internal_details(backend_client, monkeypatch):
    runtime = SimpleNamespace(
        workspace=str(backend_client.workspace),
        skills_prompt=None,
        memory_prompt=None,
        create_provider=lambda _name: object(),
        refresh_memory=lambda: None,
        create_trace=lambda _session_id: object(),
    )

    def fake_run_stream(**_kwargs):
        raise RuntimeError("token=secret C:\\private\\config.yaml")
        yield

    monkeypatch.setattr("web.backend.routers.chat.get_runtime_context", lambda: runtime)
    monkeypatch.setattr("web.backend.routers.chat.AgentService.run_stream", fake_run_stream)

    response = backend_client.post("/api/chat/runs", json={"message": "hello", "save": False})
    assert "event: run_failed" in response.text
    assert "The AI run failed" in response.text
    assert "secret" not in response.text
    assert "config.yaml" not in response.text


def test_chat_provider_error_is_generic(backend_client, monkeypatch):
    runtime = SimpleNamespace(
        workspace=str(backend_client.workspace),
        create_provider=lambda _name: (_ for _ in ()).throw(
            RuntimeError("DUMMY_API_KEY missing at C:\\private\\config.yaml")
        ),
    )
    monkeypatch.setattr("web.backend.routers.chat.get_runtime_context", lambda: runtime)

    response = backend_client.post("/api/chat/runs", json={"message": "hello"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert "DUMMY_API_KEY" not in response.text
    assert "config.yaml" not in response.text


def test_chat_session_crud_restores_only_user_visible_messages(backend_client):
    save_dir = backend_client.workspace / ".session"
    save_dir.mkdir()
    session = Session.new(str(backend_client.workspace))
    session.name = "Original"
    session.add_message("user", "Question")
    session.add_message_with_tool_calls("assistant", "", [{"id": "1"}])
    session.add_tool_message("1", "raw output")
    session.add_message("assistant", "Answer")
    session.messages[-1]["attribution"] = {
        "kind": "local",
        "sources": [{
            "source_type": "local",
            "source_id": "chunk-1",
            "title": "Lesson 1",
            "document_id": "doc-1",
            "path": "C:\\private\\lesson.md",
        }],
    }
    session.save_to_file(str(save_dir / f"{session.session_id}.json"))

    listed = backend_client.get("/api/chat/sessions").json()
    assert listed["sessions"][0]["chat_session_id"] == session.session_id

    detail = backend_client.get(f"/api/chat/sessions/{session.session_id}").json()
    assert detail["messages"] == [
        {"role": "user", "content": "Question"},
        {
            "role": "assistant",
            "content": "Answer",
            "attribution": {
                "kind": "local",
                "sources": [{
                    "source_type": "local",
                    "source_id": "chunk-1",
                    "title": "Lesson 1",
                    "document_id": "doc-1",
                }],
            },
        },
    ]
    assert "C:\\private" not in str(detail)

    renamed = backend_client.patch(
        f"/api/chat/sessions/{session.session_id}", json={"name": "Renamed"}
    )
    assert renamed.json()["name"] == "Renamed"

    deleted = backend_client.delete(f"/api/chat/sessions/{session.session_id}")
    assert deleted.json()["deleted"] is True
    assert not (save_dir / f"{session.session_id}.json").exists()


def test_session_title_generation_and_manual_name_protection(backend_client, monkeypatch):
    save_dir = backend_client.workspace / ".session"
    save_dir.mkdir(exist_ok=True)
    session = Session.new(str(backend_client.workspace))
    session.add_message("user", "Dijkstra 为什么可以使用贪心策略？")
    session.add_message("assistant", "因为非负权保证已经确定的距离不会被后续路径推翻。")
    session.save_to_file(str(save_dir / f"{session.session_id}.json"))

    provider = SimpleNamespace(complete=lambda _messages: SimpleNamespace(content="Dijkstra 的贪心正确性"))
    runtime = SimpleNamespace(create_provider=lambda _name: provider)
    monkeypatch.setattr("web.backend.routers.chat.get_runtime_context", lambda: runtime)

    titled = backend_client.post(f"/api/chat/sessions/{session.session_id}/title")
    assert titled.status_code == 200
    assert titled.json()["name"] == "Dijkstra 的贪心正确性"
    assert titled.json()["name_source"] == "ai"

    backend_client.patch(
        f"/api/chat/sessions/{session.session_id}", json={"name": "我自己的标题"}
    )
    protected = backend_client.post(f"/api/chat/sessions/{session.session_id}/title")
    assert protected.json()["name"] == "我自己的标题"
    assert protected.json()["name_source"] == "manual"


def test_old_unnamed_session_uses_local_fallback_title(backend_client):
    save_dir = backend_client.workspace / ".session"
    save_dir.mkdir(exist_ok=True)
    session = Session.new(str(backend_client.workspace))
    session.add_message("user", "请帮我整理今天需要复习的图算法重点，并给出顺序")
    session.save_to_file(str(save_dir / f"{session.session_id}.json"))

    from web.backend.routers.chat import migrate_unnamed_sessions
    assert migrate_unnamed_sessions(str(save_dir)) == 1

    detail = backend_client.get(f"/api/chat/sessions/{session.session_id}").json()
    assert detail["name"].startswith("请帮我整理今天需要复习")
    assert len(detail["name"]) <= 30
    assert detail["name_source"] == "fallback"


def test_session_title_timeout_uses_fallback(backend_client, monkeypatch):
    save_dir = backend_client.workspace / ".session"
    save_dir.mkdir(exist_ok=True)
    session = Session.new(str(backend_client.workspace))
    session.add_message("user", "解释混合检索和重排序的区别")
    session.add_message("assistant", "混合检索负责召回，重排序负责精排。")
    session.save_to_file(str(save_dir / f"{session.session_id}.json"))

    class TimeoutFuture:
        def result(self, timeout):
            assert timeout == 15
            raise TimeoutError("title timeout")

    class TimeoutExecutor:
        def __init__(self, max_workers):
            assert max_workers == 1

        def submit(self, *_args, **_kwargs):
            return TimeoutFuture()

        def shutdown(self, **_kwargs):
            return None

    runtime = SimpleNamespace(create_provider=lambda _name: object())
    monkeypatch.setattr("web.backend.routers.chat.get_runtime_context", lambda: runtime)
    monkeypatch.setattr("web.backend.routers.chat.ThreadPoolExecutor", TimeoutExecutor)

    titled = backend_client.post(f"/api/chat/sessions/{session.session_id}/title")
    assert titled.json()["name"] == "解释混合检索和重排序的区别"
    assert titled.json()["name_source"] == "fallback"


def test_quiz_recovery_and_abandon_contracts(backend_client, monkeypatch):
    monkeypatch.setattr(
        "web.backend.routers.quiz.QuizService.list_active_sessions",
        lambda self, limit: {"ok": True, "sessions": [{"practice_session_id": 7}]},
    )
    monkeypatch.setattr(
        "web.backend.routers.quiz.QuizService.get_session_state",
        lambda self, session_id: {
            "ok": True,
            "practice_session_id": session_id,
            "status": "active",
            "questions": [],
            "attempts": [],
            "progress": {"answered": 0, "total": 1},
        },
    )
    monkeypatch.setattr(
        "web.backend.routers.quiz.QuizService.abandon_session",
        lambda self, session_id: {
            "ok": True, "practice_session_id": session_id, "status": "abandoned"
        },
    )

    assert backend_client.get("/api/quiz/sessions/active").json()["sessions"][0][
        "practice_session_id"
    ] == 7
    assert backend_client.get("/api/quiz/sessions/7").json()["status"] == "active"
    assert backend_client.delete("/api/quiz/sessions/7").json()["status"] == "abandoned"


def test_review_queue_contract(backend_client, monkeypatch):
    monkeypatch.setattr(
        "web.backend.routers.learning.LearningService.get_review_queue",
        lambda self, limit: {
            "ok": True,
            "due_concepts": [{"concept": "graphs"}],
            "wrong_answers": [],
            "weaknesses": [],
        },
    )
    response = backend_client.get("/api/learning/review-queue")
    assert response.status_code == 200
    assert response.json()["due_concepts"][0]["concept"] == "graphs"


def test_library_import_strips_internal_paths(backend_client, monkeypatch):
    monkeypatch.setattr(
        "web.backend.routers.kb.KBService.import_files",
        lambda self, files, config: {
            "ok": True,
            "imported": [files[0][0]],
            "rejected": [],
            "sync": {
                "scanned_files": 1,
                "updated_files": 1,
                "chunk_count": 2,
                "relationship_count": 0,
                "graph_backend": "local",
                "rag_index_path": "C:\\private\\knowledge.db",
                "graph_store_path": "C:\\private\\graph.json",
                "error_files": 1,
                "errors": [{"source": "managed/notes.md", "error": "C:\\private\\notes.md"}],
            },
        },
    )
    response = backend_client.post(
        "/api/kb/import",
        files=[("files", ("notes.md", b"# Notes", "text/markdown"))],
    )
    assert response.status_code == 200
    assert response.json()["imported"] == ["notes.md"]
    assert "rag_index_path" not in response.text
    assert "C:\\private" not in response.text


def test_library_delete_uses_stable_contract(backend_client, monkeypatch):
    monkeypatch.setattr(
        "web.backend.routers.kb.KBService.delete_document",
        lambda self, document_id, config: {
            "ok": True,
            "document_id": document_id,
            "sync": {
                "updated_files": 1,
                "errors": [],
                "rag_index_path": "C:\\private\\knowledge.db",
            },
        },
    )

    response = backend_client.delete("/api/kb/documents/doc-1")

    assert response.status_code == 200
    assert response.json()["document_id"] == "doc-1"
    assert "rag_index_path" not in response.text
    assert "C:\\private" not in response.text


def test_memory_daily_and_promotion_strip_paths(backend_client, monkeypatch):
    monkeypatch.setattr(
        "web.backend.routers.memory.MemoryService.daily_save",
        lambda self, content, tags: {
            "ok": True, "path": "C:\\private\\daily.md", "date": "2026-07-10"
        },
    )
    monkeypatch.setattr(
        "web.backend.routers.memory.MemoryService.promote",
        lambda self, dry_run: {
            "ok": True,
            "candidates": [{"path": "C:\\private\\daily.md", "date": "2026-07-10"}],
            "promoted": 0,
            "dry_run": dry_run,
        },
    )

    saved = backend_client.post("/api/memory/daily", json={"content": "Remember"})
    promoted = backend_client.post("/api/memory/promote?dry_run=true")
    assert saved.json() == {"ok": True, "date": "2026-07-10"}
    assert "C:\\private" not in promoted.text
