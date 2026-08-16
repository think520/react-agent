"""Tests for LB-1.2 AI collaboration editing (document_proposal_service)."""

import os

import pytest

from service.document_proposal_service import (
    DocumentProposalService,
    line_diff,
    parse_proposal_response,
)


def _seed_document(workspace, document_id, source, kind, path):
    from rag.sqlite_store import KBSQLiteStore

    store = KBSQLiteStore(workspace)
    store.init_db()
    store.upsert_document(document_id=document_id, source=source, content_hash="seed", kind=kind, title="Note", path=path)
    store.close()


class _FakeProvider:
    def __init__(self, text):
        self.text = text

    def complete(self, messages, tools=None):
        from providers.types import LLMResponse
        return LLMResponse(content=self.text)


class _FakeSummary:
    def to_dict(self):
        return {}


@pytest.fixture
def svc(tmp_path, monkeypatch):
    workspace = str(tmp_path)
    sources_dir = os.path.join(workspace, ".bobodan", "sources")
    os.makedirs(sources_dir, exist_ok=True)
    note_path = os.path.join(sources_dir, "note.md")
    with open(note_path, "w", encoding="utf-8") as handle:
        handle.write("original")
    _seed_document(workspace, "doc-1", "note.md", "md", note_path)

    service = DocumentProposalService(workspace)
    monkeypatch.setattr(service.kb, "_sync_registered_sources", lambda mode, config: _FakeSummary())
    monkeypatch.setattr(service.kb, "_mark_wiki_sources_stale", lambda *a, **kw: None)
    return service


def test_parse_proposal_response():
    reason, content = parse_proposal_response("REASON: 修正公式\nCONTENT:\nnew body")
    assert reason == "修正公式"
    assert content == "new body"


def test_parse_proposal_response_fallback():
    reason, content = parse_proposal_response("just content")
    assert reason == ""
    assert content == "just content"


def test_line_diff():
    diff = line_diff("a\nb\nc", "a\nx\nc")
    kinds = [item["type"] for item in diff]
    assert "remove" in kinds and "add" in kinds


def test_create_proposal_returns_stored_proposal(svc):
    provider = _FakeProvider("REASON: 补充说明\nCONTENT:\nedited body")
    result = svc.create_proposal("doc-1", "补充说明", provider)
    assert result["ok"]
    proposal = result["proposal"]
    assert proposal["status"] == "proposed"
    assert proposal["new_content"] == "edited body"
    assert proposal["kind"] == "edit"

    loaded = svc.get_proposal(proposal["proposal_id"])
    assert loaded["ok"]
    assert loaded["proposal"]["new_content"] == "edited body"


def test_create_proposal_rejects_binary(svc, tmp_path):
    workspace = str(tmp_path)
    pdf_path = os.path.join(workspace, ".bobodan", "sources", "a.pdf")
    with open(pdf_path, "wb") as handle:
        handle.write(b"%PDF")
    _seed_document(workspace, "doc-pdf", "a.pdf", "pdf", pdf_path)

    result = DocumentProposalService(workspace).create_proposal("doc-pdf", "改", _FakeProvider("x"))
    assert not result["ok"]
    assert result["code"] == "document_read_only"


def test_apply_and_undo_edit_proposal(svc):
    result = svc.create_proposal("doc-1", "改", _FakeProvider("REASON: 改\nCONTENT:\nedited"))
    proposal_id = result["proposal"]["proposal_id"]

    applied = svc.apply_proposal(proposal_id)
    assert applied["ok"]
    assert applied["proposal"]["status"] == "applied"
    with open(os.path.join(svc.workspace, ".bobodan", "sources", "note.md"), encoding="utf-8") as handle:
        assert handle.read() == "edited"

    undone = svc.undo_proposal(proposal_id)
    assert undone["ok"]
    with open(os.path.join(svc.workspace, ".bobodan", "sources", "note.md"), encoding="utf-8") as handle:
        assert handle.read() == "original"


def test_create_new_document_proposal_apply(svc):
    result = svc.create_new_document_proposal("新笔记", "# 标题\n内容", "用户要求新建")
    assert result["ok"]
    proposal_id = result["proposal"]["proposal_id"]

    applied = svc.apply_proposal(proposal_id)
    assert applied["ok"]
    inbox = os.path.join(svc.workspace, "raw", "inbox")
    created = [name for name in os.listdir(inbox) if name.endswith(".md")]
    assert created
    with open(os.path.join(inbox, created[0]), encoding="utf-8") as handle:
        assert "# 标题" in handle.read()
