import json
import os

import pytest

from providers.types import LLMResponse
from wiki.workflow import WikiWorkflow


class FakeProvider:
    def __init__(self, pages):
        self.pages = pages

    def complete(self, messages, tools=None):
        assert "Source excerpts" in messages[0]["content"]
        return LLMResponse(content=json.dumps({"pages": self.pages}))


def source_document():
    return {
        "document_id": "doc-1",
        "title": "RAG Lesson",
        "source": "course/rag.md",
        "sections": [
            {
                "chunk_id": "chunk-1",
                "heading": "Retrieval",
                "text": "Retrieval augmented generation uses retrieved evidence.",
                "page_start": 3,
            }
        ],
    }


def test_plan_does_not_write_wiki_and_adds_bidirectional_links(tmp_path):
    vault = tmp_path / "vault"
    provider = FakeProvider([
        {
            "title": "RAG",
            "page_type": "wiki_concept",
            "summary": "A grounded generation pattern.",
            "body": "RAG combines retrieval and generation.",
            "tags": ["rag"],
            "related": ["Retriever"],
            "claims": [{"text": "It uses retrieved evidence.", "source_ids": ["S1"]}],
        },
        {
            "title": "Retriever",
            "page_type": "wiki_entity",
            "summary": "The retrieval component.",
            "body": "A retriever selects relevant chunks.",
            "tags": ["retrieval"],
            "related": [],
            "claims": [{"text": "It selects evidence.", "source_ids": ["S1"]}],
        },
    ])
    workflow = WikiWorkflow(str(tmp_path), str(vault), provider)

    plan = workflow.create_plan([source_document()])

    assert plan["status"] == "planned"
    assert plan["summary"]["add"] == 3
    assert any(item["page_type"] == "wiki_source" for item in plan["changes"])
    assert not (vault / "wiki").exists()
    retriever = next(item for item in plan["changes"] if item["title"] == "Retriever")
    assert retriever["related"] == ["RAG"]
    assert "document=doc-1" in retriever["content"]


def test_apply_writes_traceable_pages_and_checkpoint_can_restore(tmp_path):
    vault = tmp_path / "vault"
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    original = "---\ntitle: RAG\ntype: wiki_concept\ngenerated_by: bobodan\n---\n\n# RAG\n\nOld content.\n"
    page_path = concepts / "RAG.md"
    page_path.write_text(original, encoding="utf-8")
    provider = FakeProvider([{
        "title": "RAG",
        "page_type": "wiki_concept",
        "summary": "Updated summary.",
        "body": "Updated body.",
        "tags": ["rag"],
        "related": [],
        "claims": [{"text": "Grounded claim.", "source_ids": ["S1"]}],
    }])
    workflow = WikiWorkflow(str(tmp_path), str(vault), provider)
    plan = workflow.create_plan([source_document()], action="update")

    applied = workflow.apply_plan(plan["plan_id"])

    content = page_path.read_text(encoding="utf-8")
    assert applied["status"] == "applied"
    assert applied["checkpoint_id"]
    assert "source_refs:" in content
    assert "Updated body." in content
    assert "/library?collection=material&document=doc-1&chunk=chunk-1" in content

    restored = workflow.restore_checkpoint(applied["checkpoint_id"])

    assert restored["plan_id"] == plan["plan_id"]
    assert page_path.read_text(encoding="utf-8") == original


def test_manual_existing_page_is_reported_as_conflict(tmp_path):
    vault = tmp_path / "vault"
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "RAG.md").write_text("# RAG\n\nUser-authored page.", encoding="utf-8")
    provider = FakeProvider([{
        "title": "RAG",
        "page_type": "wiki_concept",
        "summary": "Summary.",
        "body": "Body.",
        "claims": [{"text": "Claim.", "source_ids": ["S1"]}],
    }])

    plan = WikiWorkflow(str(tmp_path), str(vault), provider).create_plan([source_document()])

    assert plan["summary"]["conflict"] == 1
    rag_change = next(item for item in plan["changes"] if item["title"] == "RAG")
    assert rag_change["kind"] == "conflict"


def test_same_title_source_summary_and_concept_do_not_merge(tmp_path):
    vault = tmp_path / "vault"
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "RAG.md").write_text(
        "---\ntitle: RAG\ntype: wiki_concept\ngenerated_by: bobodan\n---\n\n# RAG\n",
        encoding="utf-8",
    )
    provider = FakeProvider([{
        "title": "RAG",
        "page_type": "wiki_source",
        "summary": "Source summary.",
        "body": "Source body.",
        "claims": [{"text": "Claim.", "source_ids": ["S1"]}],
    }])

    plan = WikiWorkflow(str(tmp_path), str(vault), provider).create_plan([source_document()])

    change = next(item for item in plan["changes"] if item["page_type"] == "wiki_source")
    assert change["kind"] == "add"
    assert change["target"].startswith("sources/")


def test_failed_apply_restores_the_pre_write_checkpoint(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    page_path = concepts / "RAG.md"
    page_path.write_text("original", encoding="utf-8")
    provider = FakeProvider([{
        "title": "Retriever",
        "page_type": "wiki_entity",
        "summary": "Summary.",
        "body": "Body.",
        "claims": [{"text": "Claim.", "source_ids": ["S1"]}],
    }])
    workflow = WikiWorkflow(str(tmp_path), str(vault), provider)
    plan = workflow.create_plan([source_document()])

    def fail_after_partial_write(_plan):
        page_path.write_text("partial", encoding="utf-8")
        raise OSError("disk failure")

    monkeypatch.setattr(workflow, "_write_plan_changes", fail_after_partial_write)

    with pytest.raises(OSError, match="disk failure"):
        workflow.apply_plan(plan["plan_id"])

    assert page_path.read_text(encoding="utf-8") == "original"
    assert workflow.get_plan(plan["plan_id"])["status"] == "planned"


def test_plan_without_applicable_changes_cannot_be_applied(tmp_path):
    workflow = WikiWorkflow(str(tmp_path), str(tmp_path / "vault"), FakeProvider([]))
    plan = workflow.create_plan([source_document()])

    with pytest.raises(ValueError, match="no applicable changes"):
        workflow.apply_plan(plan["plan_id"])


def test_legacy_wiki_migration_previews_then_upgrades_metadata_only(tmp_path):
    vault = tmp_path / "vault"
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    page = concepts / "RAG.md"
    body = "# RAG\n\nUser-authored explanation."
    page.write_text(body, encoding="utf-8")
    workflow = WikiWorkflow(str(tmp_path), str(vault))

    plan = workflow.create_migration_plan()

    assert plan["status"] == "planned"
    assert plan["summary"]["update"] == 1
    assert page.read_text(encoding="utf-8") == body

    applied = workflow.apply_plan(plan["plan_id"])
    content = page.read_text(encoding="utf-8")
    assert applied["checkpoint_id"]
    assert "schema_version: 1" in content
    assert "generated_by: user" in content
    assert body in content

    workflow.restore_checkpoint(applied["checkpoint_id"])
    assert page.read_text(encoding="utf-8") == body
