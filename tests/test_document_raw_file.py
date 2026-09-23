"""原文查看：只读地取回原件，且永远不越出工作区。

解析会丢图片与表格，所以阅读侧必须能直接看文件本身（像 Obsidian 那样）。
风险面只有一个：把工作区文件读给前端。所以包含性校验是这批测试的重点。
"""

from __future__ import annotations

import os

import pytest

from service.document_edit_service import DocumentEditService


@pytest.fixture
def raw_client(tmp_path, monkeypatch):
    """A client on its own workspace: the route tests must not need a shared one."""
    monkeypatch.setenv("BOBODAN_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("BOBODAN_CONFIG", os.path.join(os.getcwd(), "config.yaml"))
    from fastapi.testclient import TestClient

    from web.backend.app import create_app
    from web.backend.deps import reset_dependency_caches

    reset_dependency_caches()
    with TestClient(create_app()) as client:
        yield client
    reset_dependency_caches()


def _workspace_with_file(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "vault").mkdir(parents=True)
    note = workspace / "vault" / "note.md"
    note.write_text("# 标题\n\n正文\n", encoding="utf-8")
    return str(workspace), str(note)


def test_the_resolver_refuses_paths_outside_the_workspace(tmp_path):
    workspace, _note = _workspace_with_file(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    service = DocumentEditService(workspace)

    assert service.resolve_source_path(str(outside)) is None
    assert service.resolve_source_path("../outside.md") is None
    assert service.resolve_source_path("") is None


def test_the_resolver_accepts_files_inside_the_workspace(tmp_path):
    workspace, note = _workspace_with_file(tmp_path)
    service = DocumentEditService(workspace)

    assert service.resolve_source_path(note) == os.path.realpath(note)
    assert service.resolve_source_path("vault/note.md") == os.path.realpath(note)


def test_raw_file_reports_the_media_type_and_name(tmp_path, monkeypatch):
    workspace, note = _workspace_with_file(tmp_path)
    service = DocumentEditService(workspace)
    monkeypatch.setattr(service, "_raw_document", lambda document_id: {"id": document_id, "path": note, "source": "vault/note.md"})

    result = service.raw_file("doc-1")

    assert result["ok"] is True
    assert result["path"] == os.path.realpath(note)
    assert result["media_type"].startswith("text/markdown")
    assert result["filename"] == "note.md"
    assert result["size"] == os.path.getsize(note)


def test_raw_file_refuses_a_file_outside_the_workspace(tmp_path, monkeypatch):
    workspace, _note = _workspace_with_file(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    service = DocumentEditService(workspace)
    monkeypatch.setattr(service, "_raw_document", lambda document_id: {"id": document_id, "path": str(outside)})

    result = service.raw_file("doc-1")

    assert result["ok"] is False
    assert result["code"] == "source_not_found"


def test_raw_file_reports_a_missing_document(tmp_path, monkeypatch):
    service = DocumentEditService(str(tmp_path))
    monkeypatch.setattr(service, "_raw_document", lambda document_id: None)

    result = service.raw_file("nope")

    assert result["ok"] is False
    assert result["code"] == "document_not_found"


def test_a_pdf_is_served_so_the_browser_can_render_it(tmp_path, monkeypatch):
    workspace, _note = _workspace_with_file(tmp_path)
    pdf = tmp_path / "ws" / "paper.pdf"  # must live inside the workspace
    pdf.write_bytes(b"%PDF-1.4 fake")
    service = DocumentEditService(workspace)
    monkeypatch.setattr(service, "_raw_document", lambda document_id: {"id": document_id, "path": str(pdf)})

    result = service.raw_file("doc-1")

    assert result["ok"] is True
    assert result["media_type"] == "application/pdf"


def test_the_raw_route_serves_the_file_inline(raw_client, tmp_path, monkeypatch):
    note = tmp_path / "note.md"
    note.write_text("# 标题", encoding="utf-8")
    monkeypatch.setattr(
        "web.backend.routers.kb.DocumentEditService.raw_file",
        lambda self, document_id: {
            "ok": True,
            "path": str(note),
            "media_type": "text/markdown; charset=utf-8",
            "filename": "note.md",
            "size": 6,
        },
    )

    response = raw_client.get("/api/kb/documents/doc-1/raw")

    assert response.status_code == 200
    assert response.text == "# 标题"
    assert "inline" in response.headers.get("content-disposition", "")


def test_an_unknown_document_is_a_404(raw_client):
    assert raw_client.get("/api/kb/documents/does-not-exist/raw").status_code == 404
