"""Tests for KBService — service layer for knowledge base operations."""

import json
import os
import pytest

from service.kb_service import KBService


def _seed_rag(workspace, documents):
    from rag.sqlite_store import KBSQLiteStore, make_chunk_row

    store = KBSQLiteStore(workspace)
    store.init_db()
    chunks = []
    for index, document in enumerate(documents):
        store.upsert_document(
            document_id=document["id"],
            source=document["source"],
            content_hash=f"hash-{index}",
            title=document["title"],
            course=document.get("course"),
            kind=document.get("kind"),
        )
        chunks.append(make_chunk_row(
            chunk_id=f"chunk-{index}",
            document_id=document["id"],
            source=document["source"],
            chunk_index=0,
            text=document["text"],
            title=document["title"],
            course=document.get("course"),
        ))
    store.insert_chunks(chunks)
    store.close()


@pytest.fixture
def workspace(tmp_path):
    return str(tmp_path)


@pytest.fixture
def svc(workspace):
    return KBService(workspace)


# --- status ---

def test_status_no_knowledge_dir(svc):
    result = svc.status()
    assert not result["ok"]
    assert "No knowledge base" in result["error"]


def test_status_with_knowledge_dir(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)

    result = svc.status()
    assert result["ok"]
    assert result["total_files"] == 0
    assert result["total_chunks"] == 0


def test_status_with_manifest(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)

    # Write a minimal manifest
    manifest = {
        "version": 1,
        "last_sync": "2026-06-12T00:00:00",
        "vault_path": "/tmp/vault",
        "documents": [
            {"source": "note1.md", "kind": "note", "title": "Note 1", "course": "CS101", "status": "ok", "chunk_count": 5},
            {"source": "note2.md", "kind": "note", "title": "Note 2", "course": "CS101", "status": "ok", "chunk_count": 3},
            {"source": "doc1.md", "kind": "course", "title": "Doc 1", "course": "CS102", "status": "ok", "chunk_count": 8},
        ],
    }
    with open(os.path.join(knowledge_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)

    from service.concept_service import ConceptService

    concepts = ConceptService(workspace)
    python = concepts.upsert_concept(name="Python", level="core")["concept"]
    java = concepts.upsert_concept(name="Java", level="core")["concept"]
    concepts.add_relationship(
        from_id=python["concept_id"],
        to_id=java["concept_id"],
        rel_type="对比",
    )

    result = svc.status()
    assert result["ok"]
    assert result["total_files"] == 3
    assert result["total_chunks"] == 16
    assert result["graph_nodes"] == 2
    assert result["graph_relationships"] == 1
    assert result["graph_nodes_by_type"]["core"] == 2
    assert len(result["courses"]) == 2


# --- search ---

def test_search_no_index(svc):
    result = svc.search(query="test")
    assert not result["ok"]
    assert "RAG index" in result["error"]


def test_search_does_not_treat_retired_dense_index_as_available(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    with open(os.path.join(knowledge_dir, "rag_index_dense.json"), "w") as handle:
        handle.write("{}")

    result = svc.search(query="test")

    assert not result["ok"]
    assert "RAG index" in result["error"]


def test_delete_document_returns_structured_not_found_code(svc):
    result = svc.delete_document("missing")

    assert result["ok"] is False
    assert result["code"] == "document_not_found"


def test_delete_document_returns_structured_read_only_code(svc, workspace):
    _seed_rag(workspace, [{
        "id": "doc-1", "source": "external/lesson.md", "title": "Lesson",
        "text": "Read-only source",
    }])

    result = svc.delete_document("doc-1")

    assert result["ok"] is False
    assert result["code"] == "document_read_only"


def test_search_empty_query(svc, workspace):
    _seed_rag(workspace, [])

    result = svc.search(query="")
    assert not result["ok"]
    assert "query" in result["error"].lower()


def test_search_with_index(svc, workspace):
    _seed_rag(workspace, [
        {"id": "doc-1", "source": "note1.md", "title": "Python", "course": "CS101", "text": "Python is a programming language"},
        {"id": "doc-2", "source": "note2.md", "title": "Java", "course": "CS101", "text": "Java is also a programming language"},
    ])

    result = svc.search(query="Python programming", top_k=5)
    assert result["ok"]
    assert len(result["results"]) > 0


def test_search_respects_selected_document_ids(svc, workspace):
    _seed_rag(workspace, [
        {"id": "doc-1", "source": "course/one.md", "title": "One", "text": "Graph shortest path algorithm"},
        {"id": "doc-2", "source": "course/two.md", "title": "Two", "text": "Graph shortest path algorithm"},
    ])
    documents = svc.list_documents()["documents"]
    allowed = next(item["document_id"] for item in documents if item["title"] == "One")

    result = svc.search("shortest path", document_ids=[allowed], top_k=5)

    assert result["ok"]
    assert result["results"]
    assert {item["document_id"] for item in result["results"]} == {allowed}


def test_search_prefers_selected_documents_without_excluding_the_library(svc, workspace):
    _seed_rag(workspace, [
        {"id": "doc-1", "source": "course/one.md", "title": "One", "text": "Graph shortest path algorithm"},
        {"id": "doc-2", "source": "course/two.md", "title": "Two", "text": "Graph shortest path algorithm"},
    ])
    documents = svc.list_documents()["documents"]
    preferred = next(item["document_id"] for item in documents if item["title"] == "Two")

    result = svc.search("shortest path", preferred_document_ids=[preferred], top_k=5)

    assert result["ok"]
    assert {item["document_id"] for item in result["results"]} == {item["document_id"] for item in documents}
    assert result["results"][0]["document_id"] == preferred


def test_wiki_run_starts_in_background_and_persists_completion(svc, monkeypatch):
    import time
    from wiki.reliability import atomic_json

    document = {
        "document_id": "doc-1", "title": "Lesson", "source": "raw/inbox/lesson.md",
        "sections": [{"chunk_id": "chunk-1", "text": "Grounded lesson."}],
    }
    coverage = [{
        "document_id": "doc-1", "status": "uncovered", "source_page_id": None,
        "linked_page_count": 0, "source_fingerprint": "abc", "covered_at": None,
    }]
    monkeypatch.setattr(svc, "_wiki_run_documents", lambda *args, **kwargs: ([document], coverage))

    def finish(self, documents, *, run_id, progress, **kwargs):
        plan = {
            "plan_id": run_id, "run_id": run_id, "status": "planned", "action": "generate",
            "instruction": "", "created_at": "2026-07-14T00:00:00Z",
            "scope": {"mode": "uncovered", "document_ids": ["doc-1"], "documents": ["Lesson"]},
            "batches": [],
            "summary": {"add": 1, "update": 0, "merge": 0, "conflict": 0, "skip": 0, "split": 0},
            "changes": [],
        }
        atomic_json(self.workflow._plan_path(run_id), plan)
        progress(status="planned", phase="planned", plan_id=run_id, plan=plan)
        return plan

    monkeypatch.setattr("wiki.orchestration.WikiOrchestrator.create_plan", finish)

    started = svc.start_wiki_run(object(), scope_mode="uncovered")

    assert started["ok"]
    assert started["status"] == "planning"
    for _ in range(50):
        current = svc.get_wiki_run(started["run_id"])
        if current.get("status") == "planned":
            break
        time.sleep(0.01)
    assert current["status"] == "planned"
    assert current["plan_id"] == started["run_id"]


def test_standard_wiki_run_only_schedules_next_five_documents(svc, monkeypatch):
    documents = [{
        "document_id": f"doc-{index}", "title": f"Lesson {index}", "source": f"raw/{index}.md",
        "sections": [{"chunk_id": f"chunk-{index}", "text": "Grounded lesson."}],
    } for index in range(8)]
    coverage = [{
        "document_id": item["document_id"], "status": "uncovered", "source_page_id": None,
        "linked_page_count": 0, "source_fingerprint": str(index), "covered_at": None,
    } for index, item in enumerate(documents)]
    monkeypatch.setattr(svc, "_wiki_run_documents", lambda *args, **kwargs: (documents, coverage))
    monkeypatch.setattr("wiki.orchestration.WikiOrchestrator.create_plan", lambda *args, **kwargs: {})

    started = svc.start_wiki_run(object(), scope_mode="uncovered", generation_mode="standard")

    assert len(started["scope"]["document_ids"]) == 5
    assert started["remaining_document_ids"] == ["doc-5", "doc-6", "doc-7"]
    assert started["budget"]["max_requests"] == 24


def test_resume_wiki_run_only_grants_remaining_plus_added_budget(svc, monkeypatch):
    from wiki.orchestration import WikiRunStore

    store = WikiRunStore(svc.workspace)
    run = store.create({
        "request": {"scope_mode": "uncovered", "generation_mode": "standard"},
        "budget": {"max_requests": 24, "max_input_tokens": 300000, "max_output_tokens": 40000},
        "usage": {"requests": 24, "input_tokens": 250000, "output_tokens": 30000},
    })
    store.update(run["run_id"], status="paused_budget")
    captured = {}

    def restart(_provider, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "run_id": "replacement"}

    monkeypatch.setattr(svc, "start_wiki_run", restart)
    result = svc.resume_wiki_run(run["run_id"], object(), {
        "max_requests": 12, "max_input_tokens": 100000, "max_output_tokens": 10000,
    })

    assert result["ok"] is True
    assert captured["budget"] == {
        "max_requests": 12,
        "max_input_tokens": 150000,
        "max_output_tokens": 20000,
    }


def test_smart_wiki_scope_does_not_fall_back_to_the_whole_library_when_topic_search_fails(svc, monkeypatch):
    documents = [
        {"document_id": "doc-1", "title": "LangChain", "source": "raw/langchain.md", "sections": [{"chunk_id": "c1", "text": "Chains"}]},
        {"document_id": "doc-2", "title": "Dijkstra", "source": "raw/dijkstra.md", "sections": [{"chunk_id": "c2", "text": "Graphs"}]},
    ]
    monkeypatch.setattr(svc, "_all_wiki_materials", lambda: documents)
    monkeypatch.setattr(svc, "search", lambda **kwargs: {"ok": False, "error": "index unavailable"})

    selected, _coverage = svc._wiki_run_documents("smart_library", topic="Transformer")

    assert selected == []


def test_search_top_k_clamped(svc, workspace):
    _seed_rag(workspace, [])

    result = svc.search(query="test", top_k=100)
    assert result["ok"]
    assert result["results"] == []


def test_legacy_index_is_not_used_as_live_library_data(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    index_path = os.path.join(knowledge_dir, "rag_index.json")
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump({"chunks": [{
            "id": "obsidian/course/lesson.md#0",
            "source": "obsidian/course/lesson.md",
            "text": "# Lesson\n\nLegacy knowledge remains readable.",
            "metadata": {
                "kind": "obsidian_note",
                "title": "Lesson",
                "course": "CS101",
                "heading_text": "Introduction",
            },
        }]}, handle)

    assert svc.list_documents()["documents"] == []
    assert not svc.search("Legacy knowledge")["ok"]
    assert os.path.exists(index_path)


def test_document_collections_hide_metadata_and_deduplicate_wiki(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    documents = []
    for index, (source, title, kind) in enumerate([
        ("obsidian/course/lesson.md", "Lesson", "obsidian_note"),
        ("obsidian/wiki/index.md", "Wiki Index", "obsidian_note"),
        ("obsidian/wiki/entities/Dijkstra算法.md", "Dijkstra算法", "wiki_entity"),
        ("obsidian/wiki/entities/Dijkstra 算法.md", "Dijkstra 算法", "wiki_entity"),
        ("obsidian/wiki/sources/2026-07-17_Dijkstra算法.md", "Dijkstra算法", "wiki_source"),
    ]):
        documents.append({
            "id": f"doc-{index}", "source": source, "title": title,
            "text": title, "kind": kind,
        })
    _seed_rag(workspace, documents)

    materials = svc.list_documents(collection="material")["documents"]
    wiki = svc.list_documents(collection="wiki")["documents"]

    assert [item["title"] for item in materials] == ["Lesson"]
    assert len(wiki) == 2
    assert {item["wiki_type"] for item in wiki} == {"entity", "source"}
    assert len({item["canonical_id"] for item in wiki}) == 2
    assert all(item["canonical_id"].startswith("wiki-") for item in wiki)
    assert svc.list_documents(collection="invalid")["ok"] is False


def test_wiki_duplicate_migration_archives_generated_pages_and_rebuilds_index(svc, workspace):
    vault = os.path.join(workspace, "note", "vault")
    entities = os.path.join(vault, "wiki", "entities")
    concepts = os.path.join(vault, "wiki", "concepts")
    os.makedirs(entities)
    os.makedirs(concepts)
    stale = os.path.join(entities, "优先队列.md")
    canonical = os.path.join(concepts, "优先队列.md")
    with open(stale, "w", encoding="utf-8") as handle:
        handle.write("---\ngenerated_by: bobodan\ntitle: 优先队列\ntype: wiki_entity\n---\n\n旧页面")
    with open(canonical, "w", encoding="utf-8") as handle:
        handle.write("---\ngenerated_by: bobodan\nindexable: true\ntitle: 优先队列\ntype: wiki_concept\ntags: [数据结构]\n---\n\n规范页面")

    result = svc.archive_duplicate_wiki_pages()

    assert result["ok"]
    assert not os.path.exists(stale)
    assert os.path.exists(canonical)
    archived = result["results"][0]["archive_dir"]
    assert os.path.exists(os.path.join(archived, "entities", "优先队列.md"))
    index = open(os.path.join(vault, "wiki", "index.md"), encoding="utf-8").read()
    assert index.count("[[优先队列]]") == 1


def test_wiki_health_and_maintenance_use_workspace_vault(svc, workspace):
    concepts = os.path.join(workspace, "note", "vault", "wiki", "concepts")
    os.makedirs(concepts)
    with open(os.path.join(concepts, "RAG.md"), "w", encoding="utf-8") as handle:
        handle.write("---\ngenerated_by: bobodan\ntitle: RAG\ntype: wiki_concept\n---\n\n# RAG")

    health = svc.wiki_health()
    maintained = svc.maintain_wiki("organize")

    assert health["ok"]
    assert health["total_pages"] == 1
    assert health["vaults"][0]["vault"] == "note/vault"
    assert maintained["ok"]
    assert maintained["canonical_count"] == 1
    assert maintained["health"]["total_pages"] == 1
    assert svc.maintain_wiki("invalid")["ok"] is False


def test_document_impact_lists_dependent_wiki_pages(svc, workspace):
    concepts = os.path.join(workspace, "note", "vault", "wiki", "concepts")
    os.makedirs(concepts)
    with open(os.path.join(concepts, "Only.md"), "w", encoding="utf-8") as handle:
        handle.write(
            "---\ntitle: Only\ntype: wiki_concept\nsource_refs:\n"
            "  - {document_id: doc-1, source: course/a.md}\n---\n\n# Only"
        )
    with open(os.path.join(concepts, "Shared.md"), "w", encoding="utf-8") as handle:
        handle.write(
            "---\ntitle: Shared\ntype: wiki_concept\nsource_refs:\n"
            "  - {document_id: doc-1, source: course/a.md}\n"
            "  - {document_id: doc-2, source: course/b.md}\n---\n\n# Shared"
        )

    impact = svc.document_impact("doc-1", document={"title": "A", "source": "course/a.md"})

    assert impact["ok"]
    assert impact["affected_count"] == 2
    actions = {item["title"]: item["action"] for item in impact["affected_pages"]}
    assert actions == {"Only": "archive_candidate", "Shared": "mark_needs_update"}


def test_mark_wiki_sources_stale_uses_resolved_legacy_vault(svc, workspace):
    concepts = os.path.join(workspace, "note", "vault", "wiki", "concepts")
    os.makedirs(concepts)
    page = os.path.join(concepts, "Lesson.md")
    with open(page, "w", encoding="utf-8") as handle:
        handle.write(
            "---\ntitle: Lesson\ntype: wiki_concept\nstatus: active\nsource_refs:\n"
            "  - {document_id: doc-1, source: course/lesson.md}\n---\n\n# Lesson"
        )

    svc._mark_wiki_sources_stale("doc-1", "course/lesson.md")

    with open(page, "r", encoding="utf-8") as handle:
        assert "status: needs_update" in handle.read()


def test_failed_apply_task_can_be_retried(svc, workspace, monkeypatch):
    from wiki.reliability import WikiTaskStore, atomic_json

    store = WikiTaskStore(workspace)
    atomic_json(store.path, [{
        "task_id": "failed-task",
        "operation": "apply",
        "status": "failed",
        "retryable": True,
        "payload": {"plan_id": "plan-1"},
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }])
    monkeypatch.setattr(
        svc,
        "apply_wiki_plan",
        lambda plan_id, config=None: {"ok": True, "plan_id": plan_id, "status": "applied"},
    )

    result = svc.retry_wiki_task("failed-task", config={})

    assert result["ok"]
    assert result["retry_of"] == "failed-task"
    assert result["result"]["plan_id"] == "plan-1"


def test_failed_orchestration_task_restarts_as_a_background_run(svc, workspace, monkeypatch):
    from wiki.reliability import WikiTaskStore, atomic_json

    store = WikiTaskStore(workspace)
    atomic_json(store.path, [{
        "task_id": "failed-run",
        "operation": "orchestrate",
        "status": "failed",
        "retryable": True,
        "payload": {
            "scope_mode": "smart_library", "document_ids": ["doc-1"],
            "topic": "RAG", "instruction": "整理概念",
        },
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }])
    monkeypatch.setattr(
        svc,
        "start_wiki_run",
        lambda provider, **kwargs: {"ok": True, "run_id": "new-run", "status": "planning"},
    )

    result = svc.retry_wiki_task("failed-run", llm_provider=object(), config={})

    assert result["ok"]
    assert result["result"]["run_id"] == "new-run"
    assert store.get("failed-run")["retried_by"] == "new-run"


def test_wiki_plan_requires_confirmation_before_writing(svc, workspace, monkeypatch):
    from providers.types import LLMResponse
    from rag.sqlite_store import KBSQLiteStore, make_chunk_row

    store = KBSQLiteStore(workspace)
    store.init_db()
    store.upsert_document(
        document_id="doc-1",
        source="course/rag.md",
        content_hash="hash",
        kind="course_document",
        title="RAG Lesson",
    )
    store.insert_chunks([make_chunk_row(
        chunk_id="chunk-1",
        document_id="doc-1",
        source="course/rag.md",
        chunk_index=0,
        text="RAG grounds generation with retrieved evidence.",
        heading_path=["RAG"],
        heading_text="RAG",
        heading_level=1,
        section_id="rag",
    )])
    store.close()

    class Provider:
        def complete(self, messages, tools=None):
            return LLMResponse(content=json.dumps({"pages": [{
                "title": "RAG",
                "page_type": "wiki_concept",
                "summary": "Grounded generation.",
                "body": "RAG uses retrieved evidence.",
                "claims": [{"text": "It uses evidence.", "source_ids": ["S1"]}],
            }]}))

    planned = svc.create_wiki_plan(Provider(), document_ids=["doc-1"])

    assert planned["ok"]
    assert planned["status"] == "planned"
    assert not os.path.exists(os.path.join(svc.managed_vault_dir, "wiki"))

    class Summary:
        def to_dict(self):
            return {"updated_files": 1, "errors": []}

    monkeypatch.setattr(svc, "_sync_registered_sources", lambda mode, config: Summary())
    applied = svc.apply_wiki_plan(planned["plan_id"])

    assert applied["ok"]
    assert applied["status"] == "applied"
    assert os.path.exists(os.path.join(svc.managed_vault_dir, "wiki", "concepts", "RAG.md"))


def test_search_uses_wiki_for_orientation_then_material_for_evidence(svc, workspace, monkeypatch):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    _seed_rag(workspace, [])

    documents = [
        {"document_id": "material-1", "source": "course/rag.md", "title": "RAG Lesson", "collection": "material", "wiki_type": None},
        {"document_id": "wiki-1", "source": "obsidian/wiki/concepts/RAG.md", "title": "RAG", "collection": "wiki", "wiki_type": "concept"},
    ]
    monkeypatch.setattr(svc, "list_documents", lambda collection="all", course=None: {"ok": True, "documents": documents})
    monkeypatch.setattr("rag.retriever.search_index_with_status", lambda *args, **kwargs: ([
        {"chunk_id": "material-chunk", "source": "course/rag.md", "text": "Original evidence", "metadata": {}},
        {"chunk_id": "wiki-chunk", "source": "obsidian/wiki/concepts/RAG.md", "text": "AI summary", "metadata": {}},
    ], {
        "retrieval_mode": "fts_only",
        "resolved_mode": "hybrid",
        "semantic_available": False,
        "fallback_from": None,
        "confidence": "medium",
    }))

    result = svc.search("RAG", top_k=2)

    assert result["ok"]
    assert [item["collection"] for item in result["results"]] == ["wiki", "material"]


def test_wiki_plan_requires_an_explicit_scope(svc, monkeypatch):
    monkeypatch.setattr(svc, "list_documents", lambda **kwargs: {
        "ok": True,
        "documents": [{"document_id": "doc-1", "collection": "material"}],
    })

    result = svc.create_wiki_plan(None)

    assert not result["ok"]
    assert "Select at least one" in result["error"]


def test_wiki_topic_without_original_links_does_not_fall_back_to_all_materials(svc, monkeypatch):
    monkeypatch.setattr(svc, "get_document", lambda document_id: {
        "ok": True,
        "document": {"document_id": document_id, "collection": "wiki"},
        "sections": [{"text": "A Wiki page without source links."}],
    })
    monkeypatch.setattr(svc, "list_documents", lambda **kwargs: {
        "ok": True,
        "documents": [{"document_id": "doc-1", "collection": "material"}],
    })

    assert svc._wiki_scope_documents(wiki_document_ids=["wiki-1"]) == []


def test_applied_wiki_plan_remains_successful_when_resync_is_deferred(svc, monkeypatch):
    monkeypatch.setattr(
        "wiki.workflow.WikiWorkflow.apply_plan",
        lambda self, plan_id: {
            "plan_id": plan_id,
            "status": "applied",
            "checkpoint_id": "b" * 32,
            "changes": [],
        },
    )
    monkeypatch.setattr(
        svc,
        "_sync_registered_sources",
        lambda mode, config: (_ for _ in ()).throw(RuntimeError("index busy")),
    )

    result = svc.apply_wiki_plan("a" * 32)

    assert result["ok"]
    assert result["status"] == "applied"
    assert result["sync"]["deferred"] is True


def test_regenerate_wiki_plan_reuses_scope_and_marks_old_plan_replaced(svc, monkeypatch):
    from wiki.workflow import WikiWorkflow

    old_plan_id = "a" * 32
    new_plan_id = "b" * 32
    workflow = WikiWorkflow(svc.workspace, svc._wiki_target_vault())
    os.makedirs(workflow.plan_dir, exist_ok=True)
    with open(workflow._plan_path(old_plan_id), "w", encoding="utf-8") as handle:
        json.dump({
            "plan_id": old_plan_id, "status": "planned", "action": "update",
            "instruction": "整理模型概念", "scope": {"document_ids": ["doc-1"], "documents": ["LLM"]},
            "summary": {"add": 0, "update": 1, "merge": 0, "conflict": 0, "skip": 0},
            "changes": [], "staging": [{"change_id": "change-1", "path": "draft.json", "errors": ["body shrink"]}],
        }, handle)
    captured = {}

    def create_plan(provider, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True, "plan_id": new_plan_id, "status": "planned", "action": "update",
            "instruction": kwargs["instruction"], "scope": {"document_ids": ["doc-1"], "documents": ["LLM"]},
            "summary": {"add": 0, "update": 1, "merge": 0, "conflict": 0, "skip": 0}, "changes": [],
        }

    monkeypatch.setattr(svc, "create_wiki_plan", create_plan)
    result = svc.recover_wiki_plan(old_plan_id, "regenerate", llm_provider=object())

    assert result["ok"]
    assert captured["document_ids"] == ["doc-1"]
    assert captured["action"] == "update"
    assert "不要用更短的草稿覆盖现有页面" in captured["instruction"]
    assert workflow.get_plan(old_plan_id)["status"] == "replaced"
    assert workflow.get_plan(old_plan_id)["replacement_plan_id"] == new_plan_id


def test_regenerate_orchestrated_plan_starts_a_new_background_run(svc, monkeypatch):
    from wiki.workflow import WikiWorkflow

    old_plan_id = "c" * 32
    new_run_id = "d" * 32
    workflow = WikiWorkflow(svc.workspace, svc._wiki_target_vault())
    os.makedirs(workflow.plan_dir, exist_ok=True)
    with open(workflow._plan_path(old_plan_id), "w", encoding="utf-8") as handle:
        json.dump({
            "plan_id": old_plan_id, "run_id": old_plan_id, "status": "planned", "action": "update",
            "topic": "LLM", "instruction": "整理模型概念",
            "scope": {"mode": "smart_library", "seed_document_ids": ["doc-1"], "document_ids": ["doc-1"], "documents": ["LLM"]},
            "summary": {"add": 0, "update": 1, "merge": 0, "conflict": 0, "skip": 0, "split": 0},
            "changes": [], "staging": [{"change_id": "change-1", "path": "draft.json", "errors": ["body shrink"]}],
        }, handle)
    captured = {}

    def start_run(provider, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "run_id": new_run_id, "status": "planning", "scope": {"documents": ["LLM"]}}

    monkeypatch.setattr(svc, "start_wiki_run", start_run)

    result = svc.recover_wiki_plan(old_plan_id, "regenerate", llm_provider=object())

    assert result["status"] == "planning"
    assert captured["scope_mode"] == "smart_library"
    assert captured["action"] == "update"
    assert workflow.get_plan(old_plan_id)["replacement_plan_id"] == new_run_id


def test_delete_managed_document_removes_source_and_resyncs(svc, workspace, monkeypatch):
    from rag.sqlite_store import KBSQLiteStore

    os.makedirs(svc.managed_sources_dir)
    source_path = os.path.join(svc.managed_sources_dir, "notes.md")
    with open(source_path, "w", encoding="utf-8") as handle:
        handle.write("# Notes")

    store = KBSQLiteStore(workspace)
    store.init_db()
    store.upsert_document(
        "doc-1",
        "managed/notes.md",
        "hash",
        path=source_path,
        kind="course_document",
        title="Notes",
    )
    store.close()

    class Summary:
        def to_dict(self):
            return {"updated_files": 1, "errors": []}

    monkeypatch.setattr(svc, "_sync_registered_sources", lambda mode, config: Summary())

    result = svc.delete_document("doc-1")

    assert result["ok"]
    assert not os.path.exists(source_path)


# --- reset ---

def test_reset_no_dir(svc, workspace):
    result = svc.reset()
    assert result["ok"]
    assert not os.path.exists(os.path.join(workspace, ".knowledge"))


def test_reset_with_dir(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    with open(os.path.join(knowledge_dir, "knowledge.db"), "w") as f:
        json.dump({}, f)
    legacy_path = os.path.join(knowledge_dir, "graph_store.json")
    with open(legacy_path, "w") as f:
        json.dump({"nodes": {}, "relationships": []}, f)

    result = svc.reset()
    assert result["ok"]
    assert not os.path.exists(os.path.join(knowledge_dir, "knowledge.db"))
    assert os.path.exists(legacy_path)


# --- sync error cases ---

def test_sync_invalid_mode(svc, workspace):
    result = svc.sync(vault_path="/tmp", mode="bad")
    assert not result["ok"]
    assert "mode" in result["error"].lower()


def test_sync_vault_outside_workspace(svc, workspace):
    result = svc.sync(vault_path="/nonexistent/path")
    assert not result["ok"]
    assert "access denied" in result["error"].lower() or "outside workspace" in result["error"].lower()


def test_sync_vault_not_found(svc, workspace):
    # Path inside workspace but doesn't exist
    vault_path = os.path.join(workspace, "nonexistent")
    result = svc.sync(vault_path=vault_path)
    assert not result["ok"]
    assert "not found" in result["error"].lower()


def test_sync_course_dir_not_found(svc, workspace):
    import tempfile
    # Create vault inside workspace
    vault_path = os.path.join(workspace, "vault")
    os.makedirs(vault_path)
    # Course dir inside workspace but doesn't exist
    course_dir = os.path.join(workspace, "nonexistent_course")
    result = svc.sync(vault_path=vault_path, course_dir=course_dir)
    assert not result["ok"]
    assert "not found" in result["error"].lower()


def test_sync_course_dir_outside_workspace(svc, workspace):
    import tempfile
    vault_path = os.path.join(workspace, "vault")
    os.makedirs(vault_path)
    with tempfile.TemporaryDirectory() as course_dir:
        result = svc.sync(vault_path=vault_path, course_dir=course_dir)
        assert not result["ok"]
        assert "access denied" in result["error"].lower() or "outside workspace" in result["error"].lower()


def test_import_files_uses_managed_sources_and_preserves_registered_roots(
    svc, workspace, monkeypatch
):
    vault = os.path.join(workspace, "vault")
    course = os.path.join(workspace, "course")
    os.makedirs(vault)
    os.makedirs(course)
    svc._save_source_roots({"vault_path": vault, "course_dirs": [course]})

    captured = {}

    class Summary:
        def to_dict(self):
            return {"scanned_files": 1, "errors": []}

    def fake_sync(mode, config):
        captured["roots"] = svc._registered_roots()
        return Summary()

    monkeypatch.setattr(svc, "_sync_registered_sources", fake_sync)
    result = svc.import_files([
        ("../lesson.md", b"# Lesson"),
        ("malware.exe", b"no"),
    ])

    assert result["ok"]
    assert result["imported"] == ["lesson.md"]
    assert result["rejected"][0]["reason"] == "unsupported_file_type"
    assert os.path.exists(os.path.join(svc.managed_sources_dir, "lesson.md"))
    _, roots = captured["roots"]
    assert os.path.abspath(course) in roots
    assert os.path.abspath(svc.managed_sources_dir) in roots


def test_portable_library_upload_uses_raw_inbox_without_creating_wiki_pages(tmp_path, monkeypatch):
    from service.library_service import LibraryService
    from service.kb_service import KBService

    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    portable = KBService(str(root))

    class Summary:
        def to_dict(self):
            return {"scanned_files": 1, "errors": []}

    monkeypatch.setattr(portable, "_sync_registered_sources", lambda mode, config: Summary())
    before = sorted(str(path.relative_to(root / "wiki")) for path in (root / "wiki").rglob("*.md"))

    result = portable.import_files([("lesson.md", b"# Lesson")])

    after = sorted(str(path.relative_to(root / "wiki")) for path in (root / "wiki").rglob("*.md"))
    assert result["ok"]
    assert (root / "raw" / "inbox" / "lesson.md").is_file()
    assert before == after


def test_portable_library_delete_archives_raw_and_marks_wiki_stale(tmp_path, monkeypatch):
    from rag.sqlite_store import KBSQLiteStore
    from service.library_service import LibraryService
    from service.kb_service import KBService

    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    portable = KBService(str(root))
    source = root / "raw" / "inbox" / "lesson.md"
    source.write_text("# Lesson", encoding="utf-8")
    wiki_page = root / "wiki" / "concepts" / "Lesson.md"
    wiki_page.write_text(
        "---\ntype: wiki_concept\ntitle: Lesson\nsources:\n  - course/inbox/lesson.md\nstatus: active\n---\n\n# Lesson\n",
        encoding="utf-8",
    )
    store = KBSQLiteStore(str(root))
    store.init_db()
    store.upsert_document(
        "doc-1", "course/inbox/lesson.md", "hash", path=str(source),
        kind="course_document", title="Lesson",
    )
    store.close()

    class Summary:
        def to_dict(self):
            return {"updated_files": 1, "errors": []}

    monkeypatch.setattr(portable, "_sync_registered_sources", lambda mode, config: Summary())
    result = portable.delete_document("doc-1")

    assert result["ok"]
    assert not source.exists()
    assert list((root / ".bobodan" / "archive" / "raw").rglob("lesson.md"))
    assert "status: needs_update" in wiki_page.read_text(encoding="utf-8")


def test_course_scanner_includes_docx_and_pptx(tmp_path):
    from obsidian.sync import _scan_course_files

    (tmp_path / "lesson.docx").write_bytes(b"docx")
    (tmp_path / "slides.pptx").write_bytes(b"pptx")
    (tmp_path / "ignored.exe").write_bytes(b"exe")

    sources = [item[0] for item in _scan_course_files(str(tmp_path))]
    assert sources == ["lesson.docx", "slides.pptx"]


def test_managed_source_root_uses_stable_managed_prefix(tmp_path):
    from obsidian.sync import _course_prefix

    assert _course_prefix(str(tmp_path / ".bobodan" / "sources"), "course") == "managed"
    assert _course_prefix(str(tmp_path / "course"), "course") == "course"


# ── P5G.0: extraction reports ───────────────────────────────────────────

def test_get_document_extraction_missing_document(svc):
    result = svc.get_document_extraction("missing")
    assert result["ok"] is False
    assert result["code"] == "document_not_found"


def test_get_document_extraction_returns_stored_report(svc, workspace):
    from rag.sqlite_store import KBSQLiteStore

    store = KBSQLiteStore(workspace)
    store.init_db()
    try:
        store.upsert_document(
            document_id="doc-scanned",
            source="course/scanned.pdf",
            content_hash="h1",
            title="Scanned",
            extraction={
                "status": "empty",
                "parser": "rag.parsers.pdf_parser",
                "total_units": 2,
                "extracted_units": 0,
                "empty_units": 2,
                "extracted_characters": 0,
                "image_count": 2,
                "warnings": ["scanned_or_empty_pages", "no_searchable_text"],
            },
        )
    finally:
        store.close()

    result = svc.get_document_extraction("doc-scanned")
    assert result["ok"]
    assert result["report"]["status"] == "empty"
    assert result["report"]["total_units"] == 2
    assert "scanned_or_empty_pages" in result["report"]["warnings"]


def test_public_document_includes_extraction_status(svc, workspace):
    from rag.sqlite_store import KBSQLiteStore

    store = KBSQLiteStore(workspace)
    store.init_db()
    try:
        store.upsert_document(
            document_id="doc-partial",
            source="course/mixed.pdf",
            content_hash="h2",
            title="Mixed",
            extraction={
                "status": "partial",
                "parser": "rag.parsers.pdf_parser",
                "total_units": 4,
                "extracted_units": 3,
                "empty_units": 1,
                "extracted_characters": 500,
                "image_count": 0,
                "warnings": ["scanned_or_empty_pages"],
            },
        )
    finally:
        store.close()

    result = svc.list_documents()
    assert result["ok"]
    doc = next(item for item in result["documents"] if item["document_id"] == "doc-partial")
    assert doc["extraction_status"] == "partial"
    assert doc["extraction_total_units"] == 4
    assert doc["extraction_empty_units"] == 1
