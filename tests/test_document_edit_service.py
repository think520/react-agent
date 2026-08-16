"""Tests for LB-1.1 document editing (service/document_edit_service.py)."""

import json
import os

import pytest

from service.document_edit_service import DocumentEditService, content_hash


def _seed_document(workspace, document_id, source, kind, path, title="Doc"):
    from rag.sqlite_store import KBSQLiteStore

    store = KBSQLiteStore(workspace)
    store.init_db()
    store.upsert_document(
        document_id=document_id,
        source=source,
        content_hash="seed",
        kind=kind,
        title=title,
        path=path,
    )
    store.close()


class _FakeSummary:
    def to_dict(self):
        return {"fake": True}


@pytest.fixture
def svc(tmp_path, monkeypatch):
    workspace = str(tmp_path)
    sources_dir = os.path.join(workspace, ".bobodan", "sources")
    os.makedirs(sources_dir, exist_ok=True)
    note_path = os.path.join(sources_dir, "note.md")
    with open(note_path, "w", encoding="utf-8") as handle:
        handle.write("original content")
    _seed_document(workspace, "doc-1", "note.md", "md", note_path)

    service = DocumentEditService(workspace)
    monkeypatch.setattr(
        service.kb,
        "_sync_registered_sources",
        lambda mode, config: _FakeSummary(),
    )
    monkeypatch.setattr(service.kb, "_mark_wiki_sources_stale", lambda *a, **kw: None)
    return service


def test_read_returns_content_and_editable(svc):
    result = svc.read("doc-1")
    assert result["ok"]
    assert result["editable"] is True
    assert result["content"] == "original content"
    assert result["content_hash"] == content_hash("original content")


def test_read_binary_document_is_read_only(tmp_path, monkeypatch):
    workspace = str(tmp_path)
    os.makedirs(os.path.join(workspace, ".bobodan", "sources"), exist_ok=True)
    pdf_path = os.path.join(workspace, ".bobodan", "sources", "a.pdf")
    with open(pdf_path, "wb") as handle:
        handle.write(b"%PDF")
    _seed_document(workspace, "doc-pdf", "a.pdf", "pdf", pdf_path)

    service = DocumentEditService(workspace)
    result = service.read("doc-pdf")
    assert result["ok"]
    assert result["editable"] is False
    assert result["content"] == ""


def test_edit_overwrites_and_records_version(svc):
    result = svc.edit("doc-1", "new content", expected_hash=content_hash("original content"))
    assert result["ok"]

    with open(os.path.join(svc.workspace, ".bobodan", "sources", "note.md"), encoding="utf-8") as handle:
        assert handle.read() == "new content"

    versions = svc.list_versions("doc-1")
    assert versions["ok"]
    assert len(versions["versions"]) == 1
    assert versions["versions"][0]["content_hash"] == content_hash("original content")


def test_edit_conflict_abandon(svc):
    # External change: the file changed since the client read it.
    with open(os.path.join(svc.workspace, ".bobodan", "sources", "note.md"), "w", encoding="utf-8") as handle:
        handle.write("externally changed")

    result = svc.edit("doc-1", "my edit", expected_hash=content_hash("original content"), conflict_action="abandon")
    assert not result["ok"]
    assert result["code"] == "document_conflict"
    # File untouched.
    with open(os.path.join(svc.workspace, ".bobodan", "sources", "note.md"), encoding="utf-8") as handle:
        assert handle.read() == "externally changed"


def test_edit_conflict_save_as_new(svc):
    with open(os.path.join(svc.workspace, ".bobodan", "sources", "note.md"), "w", encoding="utf-8") as handle:
        handle.write("externally changed")

    result = svc.edit("doc-1", "my edit", expected_hash=content_hash("original content"), conflict_action="save_as_new")
    assert result["ok"]
    assert result["saved_as_new"] is True
    inbox = os.path.join(svc.workspace, "raw", "inbox")
    assert any(name.startswith("note-edited") for name in os.listdir(inbox))


def test_rollback_restores_snapshot(svc):
    svc.edit("doc-1", "v1 content", expected_hash=content_hash("original content"))
    versions = svc.list_versions("doc-1")["versions"]
    first_id = versions[0]["id"]

    svc.edit("doc-1", "v2 content", expected_hash=content_hash("v1 content"))

    result = svc.rollback("doc-1", first_id)
    assert result["ok"]
    with open(os.path.join(svc.workspace, ".bobodan", "sources", "note.md"), encoding="utf-8") as handle:
        assert handle.read() == "original content"


def test_versions_capped_at_ten(svc):
    expected = content_hash("original content")
    for i in range(12):
        new = f"content {i}"
        svc.edit("doc-1", new, expected_hash=expected)
        expected = content_hash(new)

    versions = svc.list_versions("doc-1")["versions"]
    assert len(versions) == 10
