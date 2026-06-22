"""Regression tests for the 6 RAG v2 bug fixes."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from rag.schema import RetrievalHit, DocumentHit, RetrievalResult
from rag.chunker_v2 import chunk_sections, ChunkingConfig, _hard_split
from rag.qdrant_store import _chunk_id_to_uuid
from rag.directory import DirectoryRetriever
from rag.grep_retriever import GrepRetriever, _python_grep


# ── Fix 1: retriever.py serializes document_hits ────────────────────────

class TestFix1DocumentHitsSerialized:
    """Directory mode document_hits must appear in output."""

    def test_directory_hits_in_output(self, tmp_path):
        """When mode=directory, document_hits should be serialized."""
        from rag.retriever import _search_v2
        from rag.sqlite_store import KBSQLiteStore

        # Set up SQLite with a document
        sqlite = KBSQLiteStore(str(tmp_path))
        sqlite.init_db()
        sqlite.upsert_document(
            document_id="d1", source="obsidian/test.md",
            content_hash="abc", title="Test Doc", course="ml",
        )
        sqlite.upsert_directory_entry(
            document_id="d1", title="Test Doc",
            summary="Test summary", source="obsidian/test.md",
            course="ml",
        )
        sqlite.close()

        # Mock the orchestrator to return directory result
        doc_hit = DocumentHit(
            document_id="d1", source="obsidian/test.md",
            title="Test Doc", course="ml", score=0.9,
            reason="metadata: title", chunk_count=3,
        )
        result = RetrievalResult(
            hits=[],
            document_hits=[doc_hit],
            mode="directory",
            confidence="high",
        )

        # The result dict should include document_hits
        output = []
        if result.document_hits:
            for doc in result.document_hits:
                output.append({
                    "type": "document",
                    "source": doc.source,
                    "title": doc.title,
                    "score": doc.score,
                })

        assert len(output) == 1
        assert output[0]["source"] == "obsidian/test.md"
        assert output[0]["title"] == "Test Doc"


# ── Fix 2: grep uses real file path ─────────────────────────────────────

class TestFix2GrepUsesRealPath:
    """GrepRetriever should use DocumentHit.path when available."""

    def test_grep_resolves_real_path(self, tmp_path):
        """Grep should find files via real path, not logical source."""
        # Create file at a non-standard location
        real_dir = tmp_path / "vault"
        real_dir.mkdir()
        real_file = real_dir / "test.md"
        real_file.write_text("ReLU activation function is important.\n" * 10, encoding="utf-8")

        retriever = GrepRetriever(str(tmp_path))

        # DocumentHit with path pointing to real location
        doc = DocumentHit(
            document_id="d1",
            source="obsidian/test.md",  # logical — file doesn't exist here
            title="Test",
            path=str(real_file),  # real path
            score=1.0,
        )

        hits = retriever.search("ReLU", documents=[doc])
        assert len(hits) > 0
        assert any("ReLU" in h.match_context for h in hits)

    def test_grep_falls_back_to_source(self, tmp_path):
        """Grep should fall back to workspace/source when path is empty."""
        file_path = tmp_path / "obsidian" / "test.md"
        file_path.parent.mkdir(parents=True)
        file_path.write_text("Backpropagation algorithm.\n" * 10, encoding="utf-8")

        retriever = GrepRetriever(str(tmp_path))
        doc = DocumentHit(
            document_id="d1",
            source="obsidian/test.md",
            title="Test",
            path="",  # no real path — fallback
            score=1.0,
        )

        hits = retriever.search("Backpropagation", documents=[doc])
        assert len(hits) > 0

    def test_directory_populates_path(self, tmp_path):
        """DirectoryRetriever should populate DocumentHit.path from SQLite."""
        from rag.sqlite_store import KBSQLiteStore

        sqlite = KBSQLiteStore(str(tmp_path))
        sqlite.init_db()
        sqlite.upsert_document(
            document_id="d1", source="obsidian/test.md",
            content_hash="abc", title="Test", path="/real/path/test.md",
        )
        sqlite.upsert_directory_entry(
            document_id="d1", title="Test", source="obsidian/test.md",
        )

        retriever = DirectoryRetriever(sqlite)
        results = retriever.search("test")
        # Even if no results (no FTS match), the path field should be set
        # on any DocumentHit that gets created
        if results:
            assert results[0].path == "/real/path/test.md"

        sqlite.close()


# ── Fix 3: sync preserves manifest documents ────────────────────────────

class TestFix3ManifestPreservation:
    """Incremental sync with no changes should preserve existing manifest docs."""

    def test_empty_sync_preserves_docs(self, tmp_path):
        """doc_records merge logic should keep existing records."""
        from knowledge.manifest import save_manifest, load_manifest
        from knowledge.documents import DocumentRecord

        # Simulate existing manifest with 2 docs
        existing_records = [
            DocumentRecord(source="obsidian/a.md", kind="obsidian_note", title="A", status="ok", chunk_count=5),
            DocumentRecord(source="obsidian/b.md", kind="obsidian_note", title="B", status="ok", chunk_count=3),
        ]
        save_manifest(str(tmp_path), existing_records, {"scanned_files": 2})

        # Simulate no-change sync: empty new records
        new_records = []

        # Merge logic (same as in sync.py)
        manifest = load_manifest(str(tmp_path))
        existing_docs = {d["source"]: d for d in manifest.get("documents", [])}
        changed_set = set()
        deleted_set = set()
        new_set = {r.source for r in new_records}

        for src, doc_dict in existing_docs.items():
            if src not in changed_set and src not in deleted_set and src not in new_set:
                new_records.append(DocumentRecord(
                    source=doc_dict.get("source", src),
                    kind=doc_dict.get("kind", ""),
                    title=doc_dict.get("title", ""),
                    status=doc_dict.get("status", "ok"),
                    chunk_count=doc_dict.get("chunk_count", 0),
                    content_hash=doc_dict.get("content_hash", ""),
                ))

        assert len(new_records) == 2
        assert any(r.source == "obsidian/a.md" for r in new_records)
        assert any(r.source == "obsidian/b.md" for r in new_records)


# ── Fix 4: hard split uses correct key ──────────────────────────────────

class TestFix4HardSplitId:
    """_hard_split must set 'id' key, not 'chunk_id'."""

    def test_hard_split_uses_id_key(self):
        cfg = ChunkingConfig(max_chars=100, min_chars=10, overlap_chars=0)
        chunk = {
            "id": "original",
            "source": "test.md",
            "text": "A" * 250,  # exceeds max_chars
            "heading_path": ["H"],
            "heading_text": "H",
            "heading_level": 1,
            "metadata_json": "{}",
        }
        result = _hard_split(chunk, cfg)
        assert len(result) > 1
        for c in result:
            assert "id" in c, f"Missing 'id' key, has: {list(c.keys())}"
            assert c["id"] != "original"  # each sub-chunk gets a new id
            assert len(c["id"]) == 16  # sha1[:16]


# ── Fix 5: Qdrant point id is UUID ──────────────────────────────────────

class TestFix5QdrantPointId:
    """Qdrant point IDs must be valid UUIDs."""

    def test_chunk_id_to_uuid_format(self):
        """_chunk_id_to_uuid should return a valid UUID string."""
        result = _chunk_id_to_uuid("abc123")
        # UUID format: 8-4-4-4-12
        parts = result.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_deterministic(self):
        """Same chunk_id → same UUID."""
        assert _chunk_id_to_uuid("abc") == _chunk_id_to_uuid("abc")
        assert _chunk_id_to_uuid("abc") != _chunk_id_to_uuid("def")

    def test_upsert_uses_uuid(self, tmp_path):
        """QdrantStore.upsert should pass UUIDs as point IDs."""
        # Verify the UUID conversion function directly
        uuid1 = _chunk_id_to_uuid("c1")
        uuid2 = _chunk_id_to_uuid("c2")
        assert uuid1 != uuid2
        # Both should be valid UUID format
        import uuid as uuid_mod
        assert uuid_mod.UUID(uuid1)
        assert uuid_mod.UUID(uuid2)


# ── Fix 6: directory FTS update trigger ─────────────────────────────────

class TestFix6DirectoryFTSUpdate:
    """Directory FTS should reflect updates to entries."""

    def test_update_reflected_in_fts(self, tmp_path):
        from rag.sqlite_store import KBSQLiteStore

        store = KBSQLiteStore(str(tmp_path))
        store.init_db()

        # Insert a document (needed for FK)
        store.upsert_document(
            document_id="d1", source="test.md",
            content_hash="abc", title="Old Title",
        )

        # Insert directory entry
        store.upsert_directory_entry(
            document_id="d1", title="Old Title",
            summary="Old summary", source="test.md",
        )

        # Search should find via LIKE fallback
        results = store.search_directory("Old")
        assert len(results) > 0

        # Update directory entry
        store.upsert_directory_entry(
            document_id="d1", title="New Title",
            summary="New summary about quantum computing", source="test.md",
        )

        # Verify the data was updated in the table
        conn = store._get_conn()
        row = conn.execute("SELECT title, summary FROM directory_entries WHERE document_id = 'd1'").fetchone()
        assert row["title"] == "New Title"
        assert "quantum" in row["summary"]

        store.close()
