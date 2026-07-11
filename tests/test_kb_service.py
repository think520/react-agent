"""Tests for KBService — service layer for knowledge base operations."""

import json
import os
import pytest

from service.kb_service import KBService


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

    # Use real LocalGraphStore to write graph data
    from graph.local_store import LocalGraphStore
    graph_path = os.path.join(knowledge_dir, "graph_store.json")
    store = LocalGraphStore(graph_path)
    store.add_node("Concept", "Python")
    store.add_node("Concept", "Java")
    from graph.schema import node_id
    store.add_relationship(node_id("Concept", "Python"), "RELATED_TO", node_id("Concept", "Java"))
    store.save()

    result = svc.status()
    assert result["ok"]
    assert result["total_files"] == 3
    assert result["total_chunks"] == 16
    assert result["graph_nodes"] == 2
    assert result["graph_relationships"] == 1
    assert result["graph_nodes_by_type"]["Concept"] == 2
    assert len(result["courses"]) == 2


# --- search ---

def test_search_no_index(svc):
    result = svc.search(query="test")
    assert not result["ok"]
    assert "RAG index" in result["error"]


def test_search_empty_query(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    with open(os.path.join(knowledge_dir, "rag_index.json"), "w") as f:
        json.dump({"chunks": []}, f)

    result = svc.search(query="")
    assert not result["ok"]
    assert "query" in result["error"].lower()


def test_search_with_index(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)

    # Build a minimal sparse index
    from rag.vector_store import LocalVectorStore
    from rag.chunker import TextChunk

    store = LocalVectorStore(os.path.join(knowledge_dir, "rag_index.json"))
    chunks = [
        TextChunk(id="c1", text="Python is a programming language", source="note1.md", metadata={"course": "CS101"}),
        TextChunk(id="c2", text="Java is also a programming language", source="note2.md", metadata={"course": "CS101"}),
    ]
    store.upsert(chunks)

    result = svc.search(query="Python programming", top_k=5)
    assert result["ok"]
    assert len(result["results"]) > 0


def test_search_respects_selected_document_ids(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    from rag.vector_store import LocalVectorStore
    from rag.chunker import TextChunk

    store = LocalVectorStore(os.path.join(knowledge_dir, "rag_index.json"))
    store.upsert([
        TextChunk(id="c1", text="Graph shortest path algorithm", source="course/one.md", metadata={"title": "One"}),
        TextChunk(id="c2", text="Graph shortest path algorithm", source="course/two.md", metadata={"title": "Two"}),
    ])
    documents = svc.list_documents()["documents"]
    allowed = next(item["document_id"] for item in documents if item["title"] == "One")

    result = svc.search("shortest path", document_ids=[allowed], top_k=5)

    assert result["ok"]
    assert result["results"]
    assert {item["document_id"] for item in result["results"]} == {allowed}


def test_search_top_k_clamped(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    with open(os.path.join(knowledge_dir, "rag_index.json"), "w") as f:
        json.dump({"chunks": []}, f)

    result = svc.search(query="test", top_k=100)
    assert result["ok"]
    assert result["results"] == []


def test_legacy_index_documents_are_visible_and_readable(svc, workspace):
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

    listed = svc.list_documents()
    assert listed["ok"]
    assert len(listed["documents"]) == 1
    document = listed["documents"][0]
    assert document["origin"] == "legacy_index"
    assert document["managed"] is False
    assert document["chunk_count"] == 1

    detail = svc.get_document(document["document_id"])
    assert detail["ok"]
    assert detail["sections"][0]["chunk_id"] == "obsidian/course/lesson.md#0"
    assert "Legacy knowledge" in detail["sections"][0]["text"]

    deleted = svc.delete_document(document["document_id"])
    assert not deleted["ok"]
    assert "read-only" in deleted["error"]


def test_document_collections_hide_metadata_and_deduplicate_wiki(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    chunks = []
    for index, (source, title, kind) in enumerate([
        ("obsidian/course/lesson.md", "Lesson", "obsidian_note"),
        ("obsidian/wiki/index.md", "Wiki Index", "obsidian_note"),
        ("obsidian/wiki/entities/Dijkstra算法.md", "Dijkstra算法", "wiki_entity"),
        ("obsidian/wiki/entities/Dijkstra 算法.md", "Dijkstra 算法", "wiki_entity"),
    ]):
        chunks.append({
            "id": f"chunk-{index}", "source": source, "text": title,
            "metadata": {"title": title, "kind": kind},
        })
    with open(os.path.join(knowledge_dir, "rag_index.json"), "w", encoding="utf-8") as handle:
        json.dump({"chunks": chunks}, handle, ensure_ascii=False)

    materials = svc.list_documents(collection="material")["documents"]
    wiki = svc.list_documents(collection="wiki")["documents"]

    assert [item["title"] for item in materials] == ["Lesson"]
    assert len(wiki) == 1
    assert wiki[0]["canonical_id"].startswith("wiki-")
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


# --- graph_query ---

def test_graph_query_no_data(svc, workspace):
    result = svc.graph_query(concept="Python")
    assert result["ok"]
    # Local graph store returns empty when no data
    assert "relationships" in result or "nodes" in result


def test_graph_query_with_data(svc, workspace):
    from graph.store import get_graph_store

    store = get_graph_store(workspace)
    store.add_node("Concept", "Python")
    store.add_node("Concept", "Java")
    from graph.schema import node_id
    store.add_relationship(node_id("Concept", "Python"), "RELATED_TO", node_id("Concept", "Java"))
    store.save()
    if hasattr(store, "close"):
        store.close()

    result = svc.graph_query(concept="Python", intent="related", limit=10)
    assert result["ok"]
    assert len(result.get("relationships", [])) > 0


def test_graph_query_empty_concept(svc):
    result = svc.graph_query(concept="")
    assert not result["ok"]
    assert "concept" in result["error"].lower()


# --- reset ---

def test_reset_no_dir(svc, workspace):
    result = svc.reset()
    assert result["ok"]
    assert not os.path.exists(os.path.join(workspace, ".knowledge"))


def test_reset_with_dir(svc, workspace):
    knowledge_dir = os.path.join(workspace, ".knowledge")
    os.makedirs(knowledge_dir)
    with open(os.path.join(knowledge_dir, "test.json"), "w") as f:
        json.dump({}, f)

    result = svc.reset()
    assert result["ok"]
    assert not os.path.exists(knowledge_dir)


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
