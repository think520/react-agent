import json
import os

import pytest
import yaml

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


def test_invalid_plan_target_is_staged_without_writing(tmp_path):
    vault = tmp_path / "vault"
    workflow = WikiWorkflow(str(tmp_path), str(vault), FakeProvider([{
        "title": "RAG",
        "page_type": "wiki_concept",
        "summary": "Summary.",
        "body": "A sufficiently detailed body.",
        "claims": [{"text": "Claim.", "source_ids": ["S1"]}],
    }]))
    plan = workflow.create_plan([source_document()])
    change = next(item for item in plan["changes"] if item["page_type"] == "wiki_concept")
    change["target"] = "../index.md"
    with open(workflow._plan_path(plan["plan_id"]), "w", encoding="utf-8") as handle:
        json.dump(plan, handle)

    with pytest.raises(ValueError, match="validation failed"):
        workflow.apply_plan(plan["plan_id"])

    stored = workflow.get_plan(plan["plan_id"])
    assert stored["status"] == "planned"
    assert stored["staging"][0]["errors"]
    assert (tmp_path / ".bobodan" / "wiki" / "staging" / plan["plan_id"]).is_dir()
    assert not (vault / "index.md").exists()


def test_safe_update_preserves_sources_metadata_and_rebuilds_index(tmp_path):
    vault = tmp_path / "vault"
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    page_path = concepts / "RAG.md"
    page_path.write_text(
        "---\n"
        "type: wiki_concept\ntitle: RAG\nsummary: Old\nschema_version: 1\n"
        "generated_by: bobodan\ncreated: '2025-01-01'\nupdated: '2025-01-02'\n"
        "sources: [course/old.md]\nsource_refs:\n  - document_id: doc-old\n    source: course/old.md\n"
        "tags: [old]\nrelated: [Retriever]\nstatus: active\nindexable: true\n---\n\n# RAG\n\nOld grounded body.",
        encoding="utf-8",
    )
    (vault / "wiki" / "index.md").write_text(
        "# Wiki Index\n\n## 概念\n\n| 页面 | 摘要 | 来源数 | 更新时间 |\n| --- | --- | ---: | --- |\n| [[Ghost]] | stale | 1 | 2020-01-01 |\n",
        encoding="utf-8",
    )
    provider = FakeProvider([{
        "title": "RAG",
        "page_type": "wiki_concept",
        "summary": "Updated.",
        "body": "RAG combines retrieval and generation with grounded evidence for reliable answers.",
        "tags": ["new"],
        "related": ["Generator"],
        "claims": [{"text": "It uses evidence.", "source_ids": ["S1"]}],
    }])
    workflow = WikiWorkflow(str(tmp_path), str(vault), provider)
    plan = workflow.create_plan([source_document()], action="update")

    workflow.apply_plan(plan["plan_id"])

    content = page_path.read_text(encoding="utf-8")
    metadata = yaml.safe_load(content.split("---", 2)[1])
    index = (vault / "wiki" / "index.md").read_text(encoding="utf-8")
    assert metadata["created"] == "2025-01-01"
    assert metadata["sources"] == ["course/old.md", "course/rag.md"]
    assert {item["document_id"] for item in metadata["source_refs"]} == {"doc-old", "doc-1"}
    assert metadata["tags"] == ["old", "new"]
    assert metadata["related"] == ["Retriever", "Generator"]
    assert "[[RAG]]" in index
    assert "[[Ghost]]" not in index


def test_multi_source_update_rejects_abnormal_body_shrink_and_restores_checkpoint(tmp_path):
    vault = tmp_path / "vault"
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    page_path = concepts / "RAG.md"
    original = (
        "---\ntype: wiki_concept\ntitle: RAG\ngenerated_by: bobodan\n"
        "sources: [course/a.md, course/b.md]\nsource_refs:\n"
        "  - {document_id: a, source: course/a.md}\n  - {document_id: b, source: course/b.md}\n"
        "indexable: true\n---\n\n# RAG\n\n" + ("Existing evidence. " * 80)
    )
    page_path.write_text(original, encoding="utf-8")
    workflow = WikiWorkflow(str(tmp_path), str(vault), FakeProvider([{
        "title": "RAG",
        "page_type": "wiki_concept",
        "summary": "Short.",
        "body": "Too short.",
        "claims": [{"text": "Claim.", "source_ids": ["S1"]}],
    }]))
    plan = workflow.create_plan([source_document()], action="update")

    with pytest.raises(ValueError, match="unexpectedly shorter"):
        workflow.apply_plan(plan["plan_id"])

    assert page_path.read_text(encoding="utf-8") == original
    stored = workflow.get_plan(plan["plan_id"])
    assert stored["staging"][0]["errors"] == ["incoming body is unexpectedly shorter than the existing page"]
    apply_tasks = [item for item in workflow.list_tasks() if item["operation"] == "apply"]
    assert apply_tasks[0]["status"] == "failed"
    assert apply_tasks[0]["retryable"] is True
